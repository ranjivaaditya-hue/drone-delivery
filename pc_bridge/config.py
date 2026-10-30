"""Bridge configuration from .env, plus the mission profile.

The mission profile records which mission item is which (takeoff, delivery
waypoint, release command, RTL) and which servo channel and PWM mean "package
released". It comes from the Mission Planner .waypoints file when MISSION_FILE
is set. Each value can also be overridden with an environment variable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("config")

# MAVLink command ids (common.xml) used to read the mission file.
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_NAV_VTOL_TAKEOFF = 84
MAV_CMD_DO_SET_SERVO = 183
MAV_CMD_DO_REPEAT_SERVO = 184
MAV_CMD_DO_GRIPPER = 211
# The "type" word ArduPilot puts in its "Mission: <seq> <type>" STATUSTEXT for each command.
RELEASE_COMMAND_TEXT = {MAV_CMD_DO_SET_SERVO: "SetServo", MAV_CMD_DO_REPEAT_SERVO: "RepeatServo",
                        MAV_CMD_DO_GRIPPER: "Gripper"}


def is_nav_command(cmd_id: int) -> bool:
    """Same rule as AP_Mission::is_nav_cmd (MAV_CMD_NAV_LAST = 95)."""
    return cmd_id <= 95 or cmd_id in (213, 42702, 42703)


@dataclass
class MissionProfile:
    takeoff_seq: int | None = 1
    delivery_wp_seq: int | None = 3
    release_seq: int | None = 4
    rtl_seq: int | None = 5
    release_channel: int | None = None      # SERVOn output number (1-32)
    release_pwm: int | None = None          # PWM (us) that means "released"
    release_command: str = "SetServo"       # STATUSTEXT type word of the release command
    source: str = "built-in defaults (HOME, TAKEOFF, WP, DELIVERY WP, SERVO, RTL)"

    def describe(self) -> str:
        servo = (f"SERVO{self.release_channel} = {self.release_pwm} us"
                 if self.release_channel and self.release_pwm else "not configured (PWM evidence disabled)")
        return (f"mission profile from {self.source}: takeoff=#{self.takeoff_seq}, "
                f"delivery waypoint=#{self.delivery_wp_seq}, release={self.release_command} #{self.release_seq}, "
                f"rtl=#{self.rtl_seq}, release servo {servo}")


def parse_waypoints_file(path: Path) -> list[tuple[int, int, list[float]]]:
    """Parse a 'QGC WPL 110' file (what Mission Planner saves). Returns (seq, command, params[7])."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or not lines[0].startswith("QGC WPL"):
        raise ValueError(f"{path} is not a QGC WPL mission file")
    items = []
    for line in lines[1:]:
        cols = line.split()
        if len(cols) < 12:
            continue
        items.append((int(cols[0]), int(cols[3]), [float(c) for c in cols[4:11]]))
    return items


def profile_from_mission(items: list[tuple[int, int, list[float]]], release_channel: int | None = None) -> MissionProfile:
    """Work out the delivery layout from the mission items.

    takeoff      = first NAV_TAKEOFF
    release      = first DO_SET_SERVO / DO_REPEAT_SERVO / DO_GRIPPER(release) after the takeoff,
                   limited to RELEASE_SERVO_CHANNEL if that is set
    delivery WP  = the last NAV item before the release. ArduPilot runs a DO command
                   when the NAV item before it completes.
    rtl          = first NAV_RETURN_TO_LAUNCH after the release
    """
    p = MissionProfile(takeoff_seq=None, delivery_wp_seq=None, release_seq=None, rtl_seq=None)
    for seq, cmd, _ in items:
        if cmd in (MAV_CMD_NAV_TAKEOFF, MAV_CMD_NAV_VTOL_TAKEOFF):
            p.takeoff_seq = seq
            break
    after = p.takeoff_seq or 0
    for seq, cmd, prm in items:
        if seq <= after:
            continue
        is_release = (
            (cmd in (MAV_CMD_DO_SET_SERVO, MAV_CMD_DO_REPEAT_SERVO)
             and (release_channel is None or int(prm[0]) == release_channel))
            or (cmd == MAV_CMD_DO_GRIPPER and int(prm[1]) == 0)  # param2: 0 = release, 1 = grab
        )
        if is_release:
            p.release_seq = seq
            p.release_command = RELEASE_COMMAND_TEXT[cmd]
            if cmd != MAV_CMD_DO_GRIPPER:
                p.release_channel, p.release_pwm = int(prm[0]), int(prm[1])
            break
    if p.release_seq is not None:
        navs_before = [s for s, c, _ in items if is_nav_command(c) and 0 < s < p.release_seq]
        p.delivery_wp_seq = navs_before[-1] if navs_before else None
        for seq, cmd, _ in items:
            if seq > p.release_seq and cmd == MAV_CMD_NAV_RETURN_TO_LAUNCH:
                p.rtl_seq = seq
                break
    return p


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return default if not raw else raw in ("1", "true", "yes", "on")


@dataclass
class Settings:
    mavlink_connection: str = "udpin:0.0.0.0:14551"   # or a COM port, e.g. "COM5" (telemetry radio)
    mavlink_baud: int = 57600                          # serial only: must match the radio / SERIALx_BAUD
    depart_on_arm: bool = True                         # arming the drone = package picked up / departed
    target_system_id: int = 0                  # 0 = lock onto the first ArduPilot autopilot heard
    takeoff_alt_m: float = 1.5                 # relative altitude that counts as airborne
    release_pwm_tolerance: int = 100
    release_seq_fallback: bool = True
    api_base_url: str = "http://127.0.0.1:8000"
    drone_id: str = "DRONE-001"
    warehouse_phone: str = ""
    default_customer_name: str = "Demo Customer"
    default_customer_phone: str = ""
    sms_provider: str = "mock"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_messaging_service_sid: str = ""
    demo_step_seconds: float = 6.0
    data_dir: Path = PROJECT_ROOT / "pc_bridge" / "data"
    log_level: str = "INFO"
    mission: MissionProfile = field(default_factory=MissionProfile)


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or PROJECT_ROOT / ".env")
    s = Settings(
        mavlink_connection=os.getenv("MAVLINK_CONNECTION", Settings.mavlink_connection),
        target_system_id=_env_int("TARGET_SYSTEM_ID", 0),
        takeoff_alt_m=float(os.getenv("TAKEOFF_ALT_M", "1.5")),
        release_pwm_tolerance=_env_int("RELEASE_PWM_TOLERANCE", 100),
        release_seq_fallback=_env_bool("RELEASE_SEQ_FALLBACK", True),
        mavlink_baud=_env_int("MAVLINK_BAUD", 57600),
        depart_on_arm=_env_bool("DEPART_ON_ARM", True),
        api_base_url=os.getenv("API_BASE_URL", Settings.api_base_url).rstrip("/"),
        drone_id=os.getenv("DRONE_ID", "DRONE-001"),
        warehouse_phone=os.getenv("WAREHOUSE_PHONE", ""),
        default_customer_name=os.getenv("DEFAULT_CUSTOMER_NAME", "Demo Customer"),
        default_customer_phone=os.getenv("DEFAULT_CUSTOMER_PHONE", ""),
        sms_provider=os.getenv("SMS_PROVIDER", "mock").strip().lower(),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
        twilio_messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID", ""),
        demo_step_seconds=float(os.getenv("DEMO_STEP_SECONDS", "6")),
        data_dir=PROJECT_ROOT / os.getenv("BRIDGE_DATA_DIR", "pc_bridge/data"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
    s.mission = load_mission_profile()
    return s


def load_mission_profile() -> MissionProfile:
    channel_override = _env_int("RELEASE_SERVO_CHANNEL")
    mission_file = os.getenv("MISSION_FILE", "").strip()
    if mission_file:
        path = Path(mission_file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        p = profile_from_mission(parse_waypoints_file(path), channel_override)
        p.source = str(path.name)
        if p.release_seq is None:
            log.warning("No DO_SET_SERVO/DO_GRIPPER release command found after the takeoff in %s", path)
    else:
        p = MissionProfile()
    # Explicit env vars always win over the mission file.
    p.takeoff_seq = _env_int("TAKEOFF_SEQ", p.takeoff_seq)
    p.delivery_wp_seq = _env_int("DELIVERY_WP_SEQ", p.delivery_wp_seq)
    p.release_seq = _env_int("RELEASE_SEQ", p.release_seq)
    p.rtl_seq = _env_int("RTL_SEQ", p.rtl_seq)
    p.release_channel = channel_override or p.release_channel
    p.release_pwm = _env_int("RELEASE_SERVO_PWM", p.release_pwm)
    return p
