"""Regression tests on REAL ArduPilot output: deliveries flown on ArduCopter 4.7.1 SITL.

Mission: 0 HOME, 1 TAKEOFF 20 m, 2 WP, 3 WP (delivery, hold 3 s), 4 DO_SET_SERVO 9 1900, 5 RTL.
Recorded by tools/sitl_delivery_test.py:
  sitl_copter471_delivery.tlog                    fresh vehicle: SERVO9 goes 0 -> 1900 at the drop
  sitl_copter471_delivery_servo_left_open.tlog    the next delivery: SERVO9 is still 1900 from the
                                                  last drop, so servo-PWM evidence is unusable
Each scenario damages the stream to simulate a lossy ELRS link or missing telemetry streams,
then checks what the bridge concludes.
"""

import random
from pathlib import Path

import pytest

from config import MissionProfile, Settings
from mavlink_monitor import MavlinkMonitor, mavutil
from mission_state import DeliveryState as S, MissionStateMachine, StateTransition

DATA = Path(__file__).parent / "data"
TLOG = DATA / "sitl_copter471_delivery.tlog"
TLOG_SERVO_OPEN = DATA / "sitl_copter471_delivery_servo_left_open.tlog"
ALL = [S.DEPARTED, S.DELIVERING, S.PACKAGE_DELIVERED, S.RETURNING_HOME, S.COMPLETED]


def replay(drop_types=(), loss=0.0, seed=0, fallback=True, tlog=TLOG):
    mon = MavlinkMonitor(Settings(release_seq_fallback=fallback, depart_on_arm=False),
                         MissionProfile(takeoff_seq=1, delivery_wp_seq=3, release_seq=4, rtl_seq=5,
                                        release_channel=9, release_pwm=1900, source="test"))
    machine = MissionStateMachine()
    machine.bind("DEL-T", S.READY, 0.0)
    rng = random.Random(seed)
    log = mavutil.mavlink_connection(str(tlog))
    transitions, infos = [], []
    while True:
        msg = log.recv_msg()
        if msg is None:
            break
        if msg.get_type() in drop_types or rng.random() < loss:
            continue
        mon.handle_message(msg)
        while mon._queue:
            for out in machine.handle(mon._queue.popleft()):
                (transitions if isinstance(out, StateTransition) else infos).append(out)
        infos += machine.tick(msg._timestamp)
    return transitions, infos


def evidence(transitions, state):
    return next(t.evidence for t in transitions if t.to_state is state)


def test_clean_stream():
    tr, _ = replay()
    assert [t.to_state for t in tr] == ALL
    assert evidence(tr, S.PACKAGE_DELIVERED).startswith("STATUSTEXT 'Mission: 4 SetServo'")
    assert evidence(tr, S.RETURNING_HOME).startswith("STATUSTEXT 'Mission: 5 RTL'")
    # ArduCopter completes the RTL item when it has landed, just before it disarms.
    assert evidence(tr, S.COMPLETED).startswith("MISSION_ITEM_REACHED #5: RTL complete")


def test_one_shot_messages_lost():
    """STATUSTEXT and MISSION_ITEM_REACHED never arrive. The periodic streams carry everything."""
    tr, _ = replay(drop_types={"STATUSTEXT", "MISSION_ITEM_REACHED"})
    assert [t.to_state for t in tr] == ALL
    assert evidence(tr, S.PACKAGE_DELIVERED).startswith("SERVO_OUTPUT_RAW servo9_raw=1900")


def test_no_servo_stream_and_text_lost_uses_fallback():
    tr, _ = replay(drop_types={"STATUSTEXT", "MISSION_ITEM_REACHED", "SERVO_OUTPUT_RAW"})
    assert [t.to_state for t in tr] == ALL
    assert "fallback" in evidence(tr, S.PACKAGE_DELIVERED)


def test_no_release_evidence_means_no_delivery_claim():
    """With no servo PWM, no STATUSTEXT and the fallback off, the bridge must NOT say delivered."""
    tr, infos = replay(drop_types={"STATUSTEXT", "MISSION_ITEM_REACHED", "SERVO_OUTPUT_RAW"}, fallback=False)
    assert [t.to_state for t in tr] == [S.DEPARTED, S.DELIVERING]
    assert {i.event for i in infos} >= {"DELIVERY_WAYPOINT_REACHED", "RTL_BEFORE_RELEASE",
                                        "FLIGHT_ENDED_WITHOUT_RELEASE"}


def test_landed_home_without_one_shot_messages():
    """Without MISSION_ITEM_REACHED, the disarm HEARTBEAT or MISSION_CURRENT 'COMPLETE' proves the landing."""
    tr, _ = replay(drop_types={"STATUSTEXT", "MISSION_ITEM_REACHED"})
    assert evidence(tr, S.COMPLETED).startswith(("HEARTBEAT: disarmed", "MISSION_CURRENT mission_state=COMPLETE"))


def test_no_position_stream():
    tr, _ = replay(drop_types={"GLOBAL_POSITION_INT"})
    assert [t.to_state for t in tr] == ALL


@pytest.mark.parametrize("seed", range(10))
def test_random_30_percent_packet_loss(seed):
    tr, _ = replay(loss=0.30, seed=seed)
    assert [t.to_state for t in tr] == ALL  # every state, in order, exactly once


def test_servo_left_open_from_last_drop_does_not_fake_a_release():
    """SERVO9 already reads 1900 at takeoff. That must not count as the drop. The real drop
    is then confirmed by the mission ('Mission: 4 SetServo' or the fallback)."""
    tr, _ = replay(tlog=TLOG_SERVO_OPEN)
    assert [t.to_state for t in tr] == ALL
    assert not evidence(tr, S.PACKAGE_DELIVERED).startswith("SERVO_OUTPUT_RAW")
    tr, _ = replay(tlog=TLOG_SERVO_OPEN, drop_types={"STATUSTEXT"})
    assert [t.to_state for t in tr] == ALL
    assert "fallback" in evidence(tr, S.PACKAGE_DELIVERED)


@pytest.mark.parametrize("seed", range(5))
def test_servo_left_open_with_packet_loss(seed):
    tr, _ = replay(tlog=TLOG_SERVO_OPEN, loss=0.30, seed=seed)
    assert [t.to_state for t in tr] == ALL
