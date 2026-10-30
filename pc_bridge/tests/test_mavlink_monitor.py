"""Detector tests with real MAVLink2 packets (encoded, then decoded) from a fake ArduCopter."""

from config import MissionProfile, Settings
from mavlink_monitor import MavlinkMonitor, mavutil
from mission_state import MissionEvent as E

mavlink = mavutil.mavlink
AUTO, LOITER, RTL = 3, 5, 6  # ArduCopter custom_mode numbers


class FakeCopter:
    def __init__(self, sysid=1, compid=1):
        self.tx = mavlink.MAVLink(None, srcSystem=sysid, srcComponent=compid)
        self.rx = mavlink.MAVLink(None)
        self.t = 1_000.0

    def msg(self, name, *args, dt=0.1, **kw):
        self.t += dt
        m = getattr(self.tx, f"{name}_encode")(*args, **kw)
        out = self.rx.parse_buffer(m.pack(self.tx))[0]
        out._timestamp = self.t
        return out

    def hb(self, armed, mode, vtype=mavlink.MAV_TYPE_QUADROTOR, autopilot=mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA):
        return self.msg("heartbeat", vtype, autopilot, 89 | (128 if armed else 0), mode, 4 if armed else 3, 3)

    def seq(self, s, dt=0.1):
        return self.msg("mission_current", s, 5, 3, 1, dt=dt)

    def servo9(self, pwm, dt=0.1):
        return self.msg("servo_output_raw", 0, 0, 1500, 1500, 1500, 1500, 0, 0, 0, 0, servo9_raw=pwm, dt=dt)

    def alt(self, meters):
        return self.msg("global_position_int", 0, 0, 0, 0, int(meters * 1000), 0, 0, 0, 0)

    def text(self, s):
        return self.msg("statustext", 6, s.encode())

    def reached(self, s):
        return self.msg("mission_item_reached", s)


def monitor(**overrides):
    overrides.setdefault("depart_on_arm", False)   # these tests cover altitude-based takeoff detection
    s = Settings(**overrides)
    p = MissionProfile(takeoff_seq=1, delivery_wp_seq=3, release_seq=4, rtl_seq=5,
                       release_channel=9, release_pwm=1900, source="test")
    return MavlinkMonitor(s, p)


def run(mon, messages):
    for m in messages:
        mon.handle_message(m)
    return list(mon._queue)


def names(events):
    return [e.event for e in events]


def test_full_sitl_like_flight():
    v, mon = FakeCopter(), monitor()
    events = run(mon, [
        v.hb(False, LOITER), v.servo9(1100),
        v.hb(True, AUTO), v.seq(1), v.servo9(1100), v.alt(0.2), v.alt(3.0),
        v.reached(1), v.seq(2), v.text("Reached command #2"), v.seq(3),
        v.reached(3), v.text("Reached command #3"),
        v.text("Mission: 4 SetServo"), v.text("Mission: 5 RTL"), v.servo9(1900), v.seq(5),
        v.alt(10), v.hb(True, AUTO), v.hb(False, AUTO),
    ])
    assert names(events) == [E.MISSION_STARTED, E.TAKEOFF, E.EN_ROUTE, E.DELIVERY_WAYPOINT_REACHED,
                             E.PACKAGE_RELEASED, E.RTL_STARTED, E.HOME_COMPLETED]
    release = events[4]
    assert "Mission: 4 SetServo" in release.evidence


def test_lossy_link_uses_periodic_messages_only():
    """No STATUSTEXT and no MISSION_ITEM_REACHED arrive. Periodic streams are enough."""
    v, mon = FakeCopter(), monitor()
    events = run(mon, [
        v.hb(True, AUTO), v.servo9(1100), v.seq(1), v.alt(4), v.seq(2), v.seq(3), v.seq(3),
        v.seq(5), v.servo9(1900, dt=0.5), v.hb(False, AUTO),
    ])
    assert names(events) == [E.MISSION_STARTED, E.TAKEOFF, E.EN_ROUTE, E.DELIVERY_WAYPOINT_REACHED,
                             E.RTL_STARTED, E.PACKAGE_RELEASED, E.HOME_COMPLETED]
    release = [e for e in events if e.event is E.PACKAGE_RELEASED][0]
    assert release.evidence.startswith("SERVO_OUTPUT_RAW servo9_raw=1900")


def test_seq_fallback_when_no_servo_stream_and_text_lost():
    v, mon = FakeCopter(), monitor()
    msgs = [v.hb(True, AUTO), v.seq(1), v.alt(4), v.seq(2), v.seq(3), v.seq(5)]
    msgs += [v.seq(5, dt=1.0) for _ in range(4)]  # 4 s later, still no stronger evidence
    events = run(mon, msgs)
    release = [e for e in events if e.event is E.PACKAGE_RELEASED]
    assert len(release) == 1 and "fallback" in release[0].evidence


def test_fallback_can_be_disabled():
    v, mon = FakeCopter(), monitor(release_seq_fallback=False)
    msgs = [v.hb(True, AUTO), v.seq(1), v.alt(4), v.seq(2), v.seq(3), v.seq(5)] + [v.seq(5, dt=1.0) for _ in range(5)]
    assert E.PACKAGE_RELEASED not in names(run(mon, msgs))


def test_reaching_delivery_waypoint_alone_is_not_a_release():
    v, mon = FakeCopter(), monitor()
    events = run(mon, [v.hb(True, AUTO), v.seq(1), v.alt(4), v.seq(2), v.seq(3), v.reached(3),
                       v.text("Reached command #3"), v.servo9(1100), v.seq(3, dt=5)])
    assert E.DELIVERY_WAYPOINT_REACHED in names(events)
    assert E.PACKAGE_RELEASED not in names(events)


def test_servo_left_at_release_pwm_is_not_a_new_drop():
    v, mon = FakeCopter(), monitor(release_seq_fallback=False)
    events = run(mon, [v.hb(True, AUTO), v.servo9(1900), v.seq(1), v.alt(4), v.servo9(1900), v.servo9(1900)])
    assert E.PACKAGE_RELEASED not in names(events)
    events = run(mon, [v.servo9(1100), v.servo9(1900)])  # closed, then opened again: a real drop
    assert E.PACKAGE_RELEASED in names(events)


def test_failsafe_rtl_mode_before_delivery():
    v, mon = FakeCopter(), monitor()
    events = run(mon, [v.hb(True, AUTO), v.servo9(1100), v.seq(1), v.alt(4), v.seq(2), v.hb(True, RTL),
                       v.seq(2), v.alt(1), v.hb(False, RTL)])
    assert names(events) == [E.MISSION_STARTED, E.TAKEOFF, E.EN_ROUTE, E.RTL_STARTED, E.HOME_COMPLETED]
    assert "flight mode RTL" in events[3].evidence


def test_rtl_reported_again_after_mission_resumes():
    v, mon = FakeCopter(), monitor()
    events = run(mon, [v.hb(True, AUTO), v.seq(1), v.alt(4), v.seq(2), v.hb(True, RTL),   # failsafe
                       v.hb(True, AUTO), v.seq(2), v.seq(3), v.text("Mission: 4 SetServo"), v.seq(5)])
    assert names(events).count(E.RTL_STARTED) == 2


def test_ignores_gcs_and_other_systems():
    v, gcs, other = FakeCopter(), FakeCopter(sysid=255, compid=190), FakeCopter(sysid=7)
    mon = monitor()
    events = run(mon, [gcs.hb(True, AUTO, vtype=mavlink.MAV_TYPE_GCS, autopilot=mavlink.MAV_AUTOPILOT_INVALID),
                       v.hb(False, LOITER), other.hb(True, AUTO), other.alt(50)])
    assert mon.target_sysid == 1 and events == []


def test_no_events_without_auto_mode():
    """Manual flights (LOITER) never trigger delivery events."""
    v, mon = FakeCopter(), monitor()
    events = run(mon, [v.hb(True, LOITER), v.servo9(1100), v.alt(5), v.servo9(1900), v.hb(False, LOITER)])
    assert events == []


def test_depart_on_arm_fires_at_arming_in_any_mode():
    v, mon = FakeCopter(), monitor(depart_on_arm=True)
    events = run(mon, [v.hb(False, LOITER), v.hb(True, LOITER), v.hb(True, LOITER)])
    assert names(events) == [E.TAKEOFF]
    assert "armed" in events[0].evidence and "DEPART_ON_ARM" in events[0].evidence


def test_depart_on_arm_then_normal_mission_continues():
    v, mon = FakeCopter(), monitor(depart_on_arm=True)
    events = run(mon, [
        v.hb(True, LOITER), v.servo9(1100), v.hb(True, AUTO), v.seq(1), v.alt(4), v.seq(2), v.seq(3),
        v.text("Mission: 4 SetServo"), v.seq(5), v.hb(False, AUTO),
    ])
    got = names(events)
    assert got[:2] == [E.TAKEOFF, E.MISSION_STARTED]          # departed first, on arming
    assert got.count(E.TAKEOFF) == 1                           # and only once
    assert [e for e in got if e in (E.EN_ROUTE, E.PACKAGE_RELEASED, E.RTL_STARTED, E.HOME_COMPLETED)] == [
        E.EN_ROUTE, E.PACKAGE_RELEASED, E.RTL_STARTED, E.HOME_COMPLETED]


def test_depart_on_arm_off_waits_for_takeoff():
    v, mon = FakeCopter(), monitor(depart_on_arm=False)
    assert run(mon, [v.hb(True, LOITER), v.hb(True, LOITER)]) == []
