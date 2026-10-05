"""Fly the delivery mission on ArduCopter SITL. This script stands in for Mission Planner.

  * connects to SITL SERIAL0 (TCP 5760), requests telemetry streams like a GCS does
  * uploads mission/delivery_mission.waypoints, arms in AUTO, waits until it disarms
  * forwards a copy of every packet to UDP 127.0.0.1:14551 (what Mission Planner's
    MAVLink Mirror does), so the bridge can be tested exactly as configured
  * records everything received to a .tlog, for replay tests

Usage:  python tools/sitl_delivery_test.py [--sitl tcp:127.0.0.1:5760] [--tlog out.tlog]
        [--drop 0.3] [--drop-types STATUSTEXT,MISSION_ITEM_REACHED]
--drop / --drop-types damage only the mirrored copy, to simulate a lossy ELRS link.
"""

from __future__ import annotations

import argparse
import os
import random
import socket
import struct
import sys
import time
from pathlib import Path

os.environ.setdefault("MAVLINK20", "1")
from pymavlink import mavutil  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAV = mavutil.mavlink


def load_mission(path: Path):
    items = []
    for line in path.read_text().splitlines()[1:]:
        c = line.split()
        if len(c) >= 12:
            items.append(dict(seq=int(c[0]), current=int(c[1]), frame=int(c[2]), command=int(c[3]),
                              p=[float(x) for x in c[4:8]], x=float(c[8]), y=float(c[9]), z=float(c[10]),
                              autocontinue=int(c[11])))
    return items


def set_param(m, name, value):
    for _ in range(5):
        m.mav.param_set_send(m.target_system, m.target_component, name.encode(), float(value),
                             MAV.MAV_PARAM_TYPE_REAL32)
        ack = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
        if ack and ack.param_id == name and abs(ack.param_value - value) < 1e-3:
            print(f"  param {name} = {value}")
            return
    raise RuntimeError(f"could not set {name}")


def upload_mission(m, items):
    m.mav.mission_count_send(m.target_system, m.target_component, len(items), MAV.MAV_MISSION_TYPE_MISSION)
    while True:
        msg = m.recv_match(type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"], blocking=True, timeout=10)
        if msg is None:
            raise RuntimeError("mission upload timed out")
        if msg.get_type() == "MISSION_ACK":
            if msg.type != MAV.MAV_MISSION_ACCEPTED:
                raise RuntimeError(f"mission rejected: {msg.type}")
            print(f"  mission uploaded ({len(items)} items)")
            return
        it = items[msg.seq]
        is_global = it["frame"] in (MAV.MAV_FRAME_GLOBAL, MAV.MAV_FRAME_GLOBAL_RELATIVE_ALT)
        x = int(it["x"] * 1e7) if is_global else int(it["x"])
        y = int(it["y"] * 1e7) if is_global else int(it["y"])
        m.mav.mission_item_int_send(m.target_system, m.target_component, it["seq"], it["frame"], it["command"],
                                    it["current"], it["autocontinue"], *it["p"], x, y, it["z"],
                                    MAV.MAV_MISSION_TYPE_MISSION)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitl", default="tcp:127.0.0.1:5760")
    ap.add_argument("--mirror", default="127.0.0.1:14551")
    ap.add_argument("--mission", default=str(ROOT / "mission" / "delivery_mission.waypoints"))
    ap.add_argument("--tlog", default=str(ROOT / "sitl_flight.tlog"))
    ap.add_argument("--drop", type=float, default=0.0, help="fraction of mirrored packets to drop")
    ap.add_argument("--drop-types", default="", help="comma-separated message types never mirrored")
    ap.add_argument("--timeout", type=float, default=600)
    args = ap.parse_args()

    host, port = args.mirror.split(":")
    mirror = (host, int(port))
    drop_types = {t.strip() for t in args.drop_types.split(",") if t.strip()}
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tlog = open(args.tlog, "wb")
    rng = random.Random(42)
    stats = {"mirrored": 0, "dropped": 0}

    m = mavutil.mavlink_connection(args.sitl, source_system=255, source_component=190)

    def tap(_conn, msg):  # every received packet: record it, then mirror it (maybe lossy)
        if msg.get_type() == "BAD_DATA":
            return
        raw = msg.get_msgbuf()
        tlog.write(struct.pack(">Q", int(time.time() * 1e6)) + raw)
        if msg.get_type() in drop_types or rng.random() < args.drop:
            stats["dropped"] += 1
            return
        try:
            udp.sendto(raw, mirror)
            stats["mirrored"] += 1
        except OSError:
            pass

    m.message_hooks.append(tap)
    print("Waiting for SITL heartbeat ...")
    m.wait_heartbeat(timeout=60)
    print(f"  vehicle sysid {m.target_system}, mode {m.flightmode}")
    # Stream rates similar to Mission Planner's defaults (Hz, sim time)
    for stream, rate in ((MAV.MAV_DATA_STREAM_EXTENDED_STATUS, 2), (MAV.MAV_DATA_STREAM_POSITION, 2),
                         (MAV.MAV_DATA_STREAM_RC_CHANNELS, 2), (MAV.MAV_DATA_STREAM_EXTRA1, 4),
                         (MAV.MAV_DATA_STREAM_EXTRA2, 4), (MAV.MAV_DATA_STREAM_EXTRA3, 2),
                         (MAV.MAV_DATA_STREAM_RAW_SENSORS, 1)):
        m.mav.request_data_stream_send(m.target_system, m.target_component, stream, rate, 1)

    set_param(m, "AUTO_OPTIONS", 3)       # allow arming in AUTO and taking off without raising throttle
    set_param(m, "SERVO9_FUNCTION", 0)    # plain output, so DO_SET_SERVO can drive it
    for attempt in range(5):  # a freshly wiped SITL can reject the first upload while storage initialises
        try:
            upload_mission(m, load_mission(Path(args.mission)))
            break
        except RuntimeError as exc:
            print(f"  upload attempt {attempt + 1} failed: {exc}; retrying")
            time.sleep(3)
    else:
        raise RuntimeError("mission upload failed")

    print("Setting AUTO and arming (waits for EKF/GPS) ...")
    # Re-entering AUTO is what restarts a mission that has already completed.
    m.set_mode("LOITER")
    m.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    m.set_mode("AUTO")
    deadline = time.time() + 180
    last_text = ""
    while not m.motors_armed():
        if time.time() > deadline:
            raise RuntimeError("could not arm")
        if m.flightmode != "AUTO":
            m.set_mode("AUTO")
        m.arducopter_arm()
        until = time.time() + 2.0  # one attempt every 2 s, like a pilot retrying
        while time.time() < until and not m.motors_armed():
            msg = m.recv_match(type=["STATUSTEXT", "HEARTBEAT"], blocking=True, timeout=0.5)
            if msg and msg.get_type() == "STATUSTEXT" and msg.text != last_text:
                last_text = msg.text
                print("  FC:", msg.text)
    print("ARMED in AUTO: the mission is running")

    end = time.time() + args.timeout
    while time.time() < end:
        msg = m.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "STATUSTEXT":
            print("  FC:", msg.text)
        elif t == "HEARTBEAT" and msg.get_srcComponent() == 1 and not m.motors_armed():
            print("DISARMED: the mission finished")
            break
    stop = time.time() + 5  # keep recording/mirroring: a real vehicle keeps sending after it disarms
    while time.time() < stop:
        m.recv_match(blocking=True, timeout=0.2)
    tlog.close()
    print(f"tlog: {args.tlog}  mirrored={stats['mirrored']} dropped={stats['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
