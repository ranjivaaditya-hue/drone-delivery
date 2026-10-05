from pathlib import Path

from config import parse_waypoints_file, profile_from_mission

MISSION = Path(__file__).resolve().parents[2] / "mission" / "delivery_mission.waypoints"


def test_example_mission_profile():
    p = profile_from_mission(parse_waypoints_file(MISSION))
    assert (p.takeoff_seq, p.delivery_wp_seq, p.release_seq, p.rtl_seq) == (1, 3, 4, 5)
    assert (p.release_channel, p.release_pwm, p.release_command) == (9, 1900, "SetServo")


def test_servo_lock_before_takeoff_and_close_after_drop_are_ignored(tmp_path):
    f = tmp_path / "m.waypoints"
    f.write_text("QGC WPL 110\n"
                 "0\t1\t0\t16\t0\t0\t0\t0\t1\t2\t3\t1\n"
                 "1\t0\t3\t183\t9\t1100\t0\t0\t0\t0\t0\t1\n"     # lock the latch on the ground
                 "2\t0\t3\t22\t0\t0\t0\t0\t0\t0\t15\t1\n"
                 "3\t0\t3\t16\t0\t0\t0\t0\t1\t2\t15\t1\n"
                 "4\t0\t3\t183\t9\t1900\t0\t0\t0\t0\t0\t1\n"     # drop
                 "5\t0\t3\t19\t5\t0\t0\t0\t0\t0\t0\t1\n"         # hover 5 s (LOITER_TIME)
                 "6\t0\t3\t183\t9\t1100\t0\t0\t0\t0\t0\t1\n"     # close again
                 "7\t0\t3\t20\t0\t0\t0\t0\t0\t0\t0\t1\n")
    p = profile_from_mission(parse_waypoints_file(f))
    assert (p.takeoff_seq, p.delivery_wp_seq, p.release_seq, p.rtl_seq) == (2, 3, 4, 7)
    assert (p.release_channel, p.release_pwm) == (9, 1900)


def test_gripper_release(tmp_path):
    f = tmp_path / "g.waypoints"
    f.write_text("QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t1\t2\t3\t1\n1\t0\t3\t22\t0\t0\t0\t0\t0\t0\t15\t1\n"
                 "2\t0\t3\t16\t0\t0\t0\t0\t1\t2\t15\t1\n3\t0\t3\t211\t1\t0\t0\t0\t0\t0\t0\t1\n"
                 "4\t0\t3\t20\t0\t0\t0\t0\t0\t0\t0\t1\n")
    p = profile_from_mission(parse_waypoints_file(f))
    assert (p.delivery_wp_seq, p.release_seq, p.release_command, p.rtl_seq) == (2, 3, "Gripper", 4)
    assert p.release_channel is None  # gripper PWM lives in GRIP_* params; set RELEASE_SERVO_* in .env
