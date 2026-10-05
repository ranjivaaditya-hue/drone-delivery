"""Passive MAVLink observer: turns ArduPilot telemetry into delivery mission events.

It NEVER sends anything to the vehicle. The connection is listen-only: a UDP copy
of the stream (Mission Planner's MAVLink Mirror or a MAVProxy --out), or a .tlog
file for replay. Mission Planner keeps the real connection and is not affected.

Every rule below uses messages that ArduPilot really sends. They were checked
against the ArduPilot source (Copter 4.3-4.7) and against SITL; see README section 6.

  HEARTBEAT            base_mode ARMED flag and custom_mode (flight mode). Always ~1 Hz.
                       Disarming after the return leg = home completed.
  MISSION_CURRENT      seq of the current NAV item (DO items such as DO_SET_SERVO
                       never appear here). EXT_STAT stream.
  MISSION_ITEM_REACHED seq of a completed NAV item. One-shot, so it can be lost on a lossy link.
  STATUSTEXT           "Mission: <seq> <type>" when any mission item starts
                       (type: Takeoff, WP, SetServo, Gripper, RTL, Land, ...);
                       "Reached command #<seq>" when a waypoint completes. One-shot.
  SERVO_OUTPUT_RAW     PWM actually output on each servo channel. RC_CHAN stream.
  GLOBAL_POSITION_INT  relative_alt, used only to confirm airborne. POSITION stream.
  EXTENDED_SYS_STATE   landed_state. Not in any default ArduPilot stream, so it is used only if present.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field

os.environ.setdefault("MAVLINK20", "1")  # MAVLink2 parser: needed for servo9-16 and MISSION_CURRENT extensions
from pymavlink import mavutil  # noqa: E402

from config import MissionProfile, Settings  # noqa: E402
from mission_state import DetectedEvent, MissionEvent  # noqa: E402

log = logging.getLogger("mavlink")
fc_log = logging.getLogger("fc")

RTL_MODES = {"RTL", "SMART_RTL", "AUTO_RTL", "QRTL"}
LAND_MODES = {"LAND", "QLAND"}
MAV = mavutil.mavlink
NOT_A_VEHICLE = {MAV.MAV_TYPE_GCS, MAV.MAV_TYPE_GIMBAL, MAV.MAV_TYPE_ADSB, MAV.MAV_TYPE_ONBOARD_CONTROLLER,
                 MAV.MAV_TYPE_CAMERA, MAV.MAV_TYPE_ANTENNA_TRACKER}
LANDED_AIRBORNE = {MAV.MAV_LANDED_STATE_IN_AIR, MAV.MAV_LANDED_STATE_TAKEOFF, MAV.MAV_LANDED_STATE_LANDING}
RE_MISSION_ITEM = re.compile(r"^Mission: (\d+) (\w+)")
RE_REACHED = re.compile(r"^Reached command #(\d+)")
FALLBACK_DELAY_S = 3.0           # wait for stronger release evidence before using the mission-seq fallback
LINK_REPORT_EVERY_S = 30.0
WATCHED_TYPES = ("HEARTBEAT", "MISSION_CURRENT", "SERVO_OUTPUT_RAW", "GLOBAL_POSITION_INT",
                 "MISSION_ITEM_REACHED", "STATUSTEXT", "EXTENDED_SYS_STATE")


@dataclass
class Flight:
    """Per-flight tracking, from arming to disarming."""
    started: float
    emitted: set = field(default_factory=set)       # one-shot events already emitted this flight
    seen_seq_le_takeoff: bool = False
    seen_seq_le_delivery: bool = False
    returning: bool = False                          # latch for RTL_STARTED, re-armed if the return is aborted
    servo_prev: int | None = None
    servo_non_release_seen: bool = False
    servo_stale_warned: bool = False
    fallback_pending: tuple[float, str] | None = None


class MavlinkMonitor:
    def __init__(self, settings: Settings, profile: MissionProfile):
        self.s, self.p = settings, profile
        self.conn = None
        self.is_log = False
        self.eof = False
        self.target_sysid: int | None = settings.target_system_id or None
        self.armed: bool | None = None
        self.mode: str | None = None
        self.seq: int | None = None
        self.flight: Flight | None = None
        self.last_heartbeat_wall: float | None = None
        self.last_msg_time: float | None = None
        self._queue: deque[DetectedEvent] = deque()
        self._counts: Counter = Counter()
        self._last_report = time.monotonic()

    # ------------------------------------------------------------ connection
    def open(self) -> None:
        conn_str = self.s.mavlink_connection
        log.info("Opening MAVLink (listen-only): %s", conn_str)
        log.info(self.p.describe())
        self.conn = mavutil.mavlink_connection(conn_str, robust_parsing=True)
        self.is_log = isinstance(self.conn, mavutil.mavlogfile)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()

    @property
    def vehicle_connected(self) -> bool:
        if self.is_log:
            return not self.eof
        return self.last_heartbeat_wall is not None and time.monotonic() - self.last_heartbeat_wall < 5.0

    def describe(self) -> str:
        return f"MAVLink {self.s.mavlink_connection}"

    def poll(self, timeout: float) -> DetectedEvent | None:
        """Read messages until an event is detected or `timeout` seconds pass."""
        deadline = time.monotonic() + timeout
        while not self._queue and not self.eof:
            if self.is_log:
                msg = self.conn.recv_msg()  # select() does not work on files on Windows
                if msg is None:
                    self.eof = True
                    break
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                msg = self.conn.recv_match(blocking=True, timeout=remaining)
                if msg is None:
                    break
            self.handle_message(msg)
        if not self.is_log:
            self._report_link()
        return self._queue.popleft() if self._queue else None

    # ------------------------------------------------------------ dispatch
    def handle_message(self, msg) -> None:
        mtype = msg.get_type()
        if mtype == "BAD_DATA":
            return
        t = getattr(msg, "_timestamp", None) or time.time()
        self.last_msg_time = t
        src, comp = msg.get_srcSystem(), msg.get_srcComponent()

        if self.target_sysid is None:
            if mtype == "HEARTBEAT" and comp == MAV.MAV_COMP_ID_AUTOPILOT1 and self._is_vehicle(msg):
                self.target_sysid = src
                log.info("Locked onto vehicle: system id %d (%s)", src, mavutil.mode_string_v10(msg))
            else:
                return
        if src != self.target_sysid or comp != MAV.MAV_COMP_ID_AUTOPILOT1:
            return
        self._counts[mtype] += 1

        handler = {
            "HEARTBEAT": self._on_heartbeat,
            "MISSION_CURRENT": self._on_mission_current,
            "MISSION_ITEM_REACHED": self._on_item_reached,
            "STATUSTEXT": self._on_statustext,
            "SERVO_OUTPUT_RAW": self._on_servo_output,
            "GLOBAL_POSITION_INT": self._on_global_position,
            "EXTENDED_SYS_STATE": self._on_extended_sys_state,
        }.get(mtype)
        if handler is not None and (mtype == "HEARTBEAT" or self.armed is not None):
            handler(msg, t)
        self._check_release_fallback(t)

    @staticmethod
    def _is_vehicle(msg) -> bool:
        return msg.autopilot == MAV.MAV_AUTOPILOT_ARDUPILOTMEGA and msg.type not in NOT_A_VEHICLE

    # ------------------------------------------------------------ helpers
    def _in_mission(self) -> bool:
        """Armed, and AUTO has been engaged during this flight."""
        return bool(self.armed and self.flight and MissionEvent.MISSION_STARTED in self.flight.emitted)

    def _airborne(self) -> bool:
        return bool(self.armed and self.flight and MissionEvent.TAKEOFF in self.flight.emitted)

    def _emit(self, event: MissionEvent, evidence: str, t: float, once: bool = True) -> None:
        f = self.flight
        if f is None or (once and event in f.emitted):
            return
        f.emitted.add(event)
        log.info("EVENT %-26s %s", event.value, evidence)
        self._queue.append(DetectedEvent(event, evidence, t, "MAVLINK"))

    def _takeoff(self, evidence: str, t: float) -> None:
        if self._in_mission():
            self._emit(MissionEvent.TAKEOFF, evidence, t)

    def _released(self, evidence: str, t: float) -> None:
        if self._in_mission():
            self._emit(MissionEvent.PACKAGE_RELEASED, evidence, t)

    def _returning(self, evidence: str, t: float) -> None:
        """Edge-triggered: one RTL_STARTED per return. Re-armed if the return is abandoned."""
        f = self.flight
        if f is None or not self.armed or f.returning:
            return
        f.returning = True
        self._emit(MissionEvent.RTL_STARTED, evidence, t, once=False)

    # ------------------------------------------------------------ message rules
    def _on_heartbeat(self, msg, t: float) -> None:
        if not self._is_vehicle(msg):
            return
        self.last_heartbeat_wall = time.monotonic()
        armed = bool(msg.base_mode & MAV.MAV_MODE_FLAG_SAFETY_ARMED)
        mode = mavutil.mode_string_v10(msg)
        was_armed, prev_mode = self.armed, self.mode
        self.armed, self.mode = armed, mode

        if armed and not was_armed:
            self.flight = Flight(started=t)
            log.info("Vehicle ARMED (mode %s)", mode)
        elif was_armed and not armed:
            log.info("Vehicle DISARMED (mode %s)", mode)
            if self.flight and MissionEvent.TAKEOFF in self.flight.emitted:
                self._emit(MissionEvent.HOME_COMPLETED, f"HEARTBEAT: disarmed after the flight (mode {mode})", t)
            self.flight = None
            return
        if not armed:
            return
        if mode != prev_mode and prev_mode is not None:
            log.info("Flight mode %s -> %s", prev_mode, mode)

        if mode == "AUTO":
            self._emit(MissionEvent.MISSION_STARTED, "HEARTBEAT: armed, flight mode AUTO", t)
        if mode in RTL_MODES:
            if self._in_mission():
                self._returning(f"HEARTBEAT: flight mode {mode}", t)
        elif prev_mode in RTL_MODES and mode not in LAND_MODES and self.flight:
            # Left RTL for something other than landing (pilot took over, or back to AUTO): return abandoned.
            self.flight.returning = False
        if mode in LAND_MODES and self._airborne():
            self._emit(MissionEvent.LANDING, f"HEARTBEAT: flight mode {mode}", t)

    def _on_mission_current(self, msg, t: float) -> None:
        seq = msg.seq
        prev, self.seq = self.seq, seq
        if not self.armed or self.mode != "AUTO" or self.flight is None:
            return
        f, p = self.flight, self.p
        tko = p.takeoff_seq or 0
        if seq <= tko:
            f.seen_seq_le_takeoff = True
        if p.delivery_wp_seq is not None and seq <= p.delivery_wp_seq:
            f.seen_seq_le_delivery = True

        if seq > tko:
            if f.seen_seq_le_takeoff:
                self._takeoff(f"MISSION_CURRENT advanced past the takeoff item #{tko} (now #{seq})", t)
            if self._airborne():
                self._emit(MissionEvent.EN_ROUTE, f"MISSION_CURRENT #{seq}: flying the route (takeoff item #{tko} done)", t)

        if p.delivery_wp_seq is not None and seq > p.delivery_wp_seq and self._airborne():
            self._emit(MissionEvent.DELIVERY_WAYPOINT_REACHED,
                       f"MISSION_CURRENT advanced past delivery waypoint #{p.delivery_wp_seq} (now #{seq})", t)

        # Fallback release evidence: the mission engine passed the release DO command.
        # It runs when the delivery waypoint completes, in the same step that starts the next NAV item.
        if (self.s.release_seq_fallback and p.release_seq is not None and seq > p.release_seq
                and f.seen_seq_le_delivery and MissionEvent.PACKAGE_RELEASED not in f.emitted
                and f.fallback_pending is None):
            f.fallback_pending = (t, f"MISSION_CURRENT {prev}->{seq}: mission passed release command "
                                     f"#{p.release_seq} ({p.release_command}) - fallback, no servo PWM/STATUSTEXT seen")

        # Mission finished (MAVLink2 extension field, ArduPilot 4.5+). After the return leg,
        # this means the drone landed at home. It also covers a lost "disarmed" HEARTBEAT.
        if getattr(msg, "mission_state", 0) == MAV.MISSION_STATE_COMPLETE and f.returning and self._airborne():
            self._emit(MissionEvent.HOME_COMPLETED, "MISSION_CURRENT mission_state=COMPLETE after the return leg", t)

        # Return leg: the RTL item, or the first NAV item after the release command.
        if self._is_return_seq(seq):
            self._returning(f"MISSION_CURRENT #{seq}: return item ({'RTL' if seq == p.rtl_seq else 'after release'})", t)
        elif f.returning and self.mode == "AUTO":
            f.returning = False  # mission resumed before the return leg (e.g. after a failsafe RTL)

    def _is_return_seq(self, seq: int) -> bool:
        if self.p.rtl_seq is not None:
            return seq == self.p.rtl_seq
        return self.p.release_seq is not None and seq > self.p.release_seq

    def _on_item_reached(self, msg, t: float) -> None:
        seq, p = msg.seq, self.p
        if p.takeoff_seq is not None and seq == p.takeoff_seq:
            self._takeoff(f"MISSION_ITEM_REACHED #{seq} (takeoff item)", t)
            if self._airborne():
                self._emit(MissionEvent.EN_ROUTE, f"MISSION_ITEM_REACHED #{seq}: takeoff complete", t)
        if p.delivery_wp_seq is not None and seq == p.delivery_wp_seq and self._in_mission():
            self._emit(MissionEvent.DELIVERY_WAYPOINT_REACHED, f"MISSION_ITEM_REACHED #{seq} (delivery waypoint)", t)
        if p.rtl_seq is not None and seq == p.rtl_seq and self._airborne():
            # ArduCopter completes the RTL item only after it has landed at home.
            self._returning(f"MISSION_ITEM_REACHED #{seq} (RTL item)", t)
            self._emit(MissionEvent.HOME_COMPLETED, f"MISSION_ITEM_REACHED #{seq}: RTL complete, landed at home", t)

    def _on_statustext(self, msg, t: float) -> None:
        text = (msg.text or "").rstrip("\x00").strip()
        fc_log.info("%s", text)
        if not self._in_mission():
            return
        p = self.p
        m = RE_MISSION_ITEM.match(text)
        if m:
            seq, kind = int(m.group(1)), m.group(2)
            # With a known release seq the match is exact. Without one, require airborne, so a
            # "close the latch" servo command before takeoff is not mistaken for the drop.
            if kind == p.release_command and (seq == p.release_seq if p.release_seq is not None else self._airborne()):
                self._released(f"STATUSTEXT '{text}': mission started the release command", t)
            if kind == "RTL":
                self._returning(f"STATUSTEXT '{text}'", t)
            if kind == "Land" and self._airborne():
                self._emit(MissionEvent.LANDING, f"STATUSTEXT '{text}'", t)
            if seq > (p.takeoff_seq or 0) and self._airborne():
                self._emit(MissionEvent.EN_ROUTE, f"STATUSTEXT '{text}': takeoff item done", t)
            return
        m = RE_REACHED.match(text)
        if m and p.delivery_wp_seq is not None and int(m.group(1)) == p.delivery_wp_seq:
            self._emit(MissionEvent.DELIVERY_WAYPOINT_REACHED, f"STATUSTEXT '{text}' (delivery waypoint)", t)

    def _on_servo_output(self, msg, t: float) -> None:
        ch, target = self.p.release_channel, self.p.release_pwm
        if not ch or not target or self.flight is None:
            return
        port, idx = divmod(ch - 1, 16)
        if getattr(msg, "port", 0) != port:
            return
        pwm = getattr(msg, f"servo{idx + 1}_raw", None)
        if pwm is None:
            return
        f = self.flight
        is_release = abs(pwm - target) <= self.s.release_pwm_tolerance
        if not is_release:
            f.servo_non_release_seen = True
        elif not f.servo_non_release_seen:
            if not f.servo_stale_warned:
                f.servo_stale_warned = True
                log.warning("SERVO%d is already at the release PWM (%d us) this flight. It was probably left there "
                            "by the last drop. Servo-PWM evidence waits until it returns to the closed position.",
                            ch, pwm)
        elif self._in_mission():
            self._released(f"SERVO_OUTPUT_RAW servo{ch}_raw={pwm} us (release {target}±{self.s.release_pwm_tolerance}, "
                           f"was {f.servo_prev} us)", t)
        f.servo_prev = pwm

    def _on_global_position(self, msg, t: float) -> None:
        alt_m = msg.relative_alt / 1000.0
        if alt_m >= self.s.takeoff_alt_m:
            self._takeoff(f"GLOBAL_POSITION_INT relative_alt={alt_m:.1f} m", t)

    def _on_extended_sys_state(self, msg, t: float) -> None:
        if msg.landed_state in LANDED_AIRBORNE:
            self._takeoff(f"EXTENDED_SYS_STATE landed_state={msg.landed_state}", t)
        if msg.landed_state == MAV.MAV_LANDED_STATE_LANDING and self._airborne():
            self._emit(MissionEvent.LANDING, "EXTENDED_SYS_STATE landed_state=LANDING", t)

    def _check_release_fallback(self, t: float) -> None:
        f = self.flight
        if f is None or f.fallback_pending is None:
            return
        if MissionEvent.PACKAGE_RELEASED in f.emitted:
            f.fallback_pending = None
        elif t - f.fallback_pending[0] >= FALLBACK_DELAY_S:
            evidence = f.fallback_pending[1]
            f.fallback_pending = None
            self._released(evidence, t)

    # ------------------------------------------------------------ link report
    def _report_link(self) -> None:
        now = time.monotonic()
        if now - self._last_report < LINK_REPORT_EVERY_S:
            return
        span = now - self._last_report
        self._last_report = now
        if self.target_sysid is None:
            log.warning("No ArduPilot HEARTBEAT received yet on %s. Check that the MAVLink copy is being sent "
                        "to this port (see README section 5).", self.s.mavlink_connection)
            return
        rates = ", ".join(f"{k} {self._counts.get(k, 0) / span:.1f}/s" for k in WATCHED_TYPES)
        log.info("Link check: %s", rates)
        for needed, why in (("MISSION_CURRENT", "mission progress (EXT_STAT stream)"),
                            ("SERVO_OUTPUT_RAW", "servo-PWM release evidence (RC_CHAN stream)")):
            if self._counts.get(needed, 0) == 0:
                log.warning("Not receiving %s, needed for %s. Raise that stream rate (see README section 5).",
                            needed, why)
        self._counts.clear()
