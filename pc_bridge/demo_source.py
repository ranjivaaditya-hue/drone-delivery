"""DemoEventSource: plays a complete delivery mission without a drone.

It emits the same MissionEvents as the MAVLink monitor. Everything downstream
(state machine, SMS, API, Android app) therefore behaves exactly as it would on a
real flight. PACKAGE_RELEASED is emitted three times, the way a telemetry stream
can repeat evidence, to show that this still produces only one SMS.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from mission_state import DetectedEvent, MissionEvent as E

log = logging.getLogger("demo")

# (delay before this event, in units of DEMO_STEP_SECONDS; event; evidence)
SCRIPT = [
    (0.0, E.MISSION_STARTED, "demo: armed, flight mode AUTO"),
    (0.5, E.TAKEOFF, "demo: airborne (relative altitude 2.0 m)"),
    (1.0, E.EN_ROUTE, "demo: takeoff item #1 done, flying to waypoint #2"),
    (2.0, E.DELIVERY_WAYPOINT_REACHED, "demo: reached delivery waypoint #3"),
    (0.7, E.PACKAGE_RELEASED, "demo: SERVO9 output 1900 us (DO_SET_SERVO #4)"),
    (0.1, E.PACKAGE_RELEASED, "demo: repeated release evidence (must be ignored)"),
    (0.1, E.PACKAGE_RELEASED, "demo: repeated release evidence (must be ignored)"),
    (1.0, E.RTL_STARTED, "demo: mission item #5 RTL started"),
    (2.0, E.LANDING, "demo: landing at home"),
    (0.8, E.HOME_COMPLETED, "demo: disarmed at home"),
]


class DemoEventSource:
    def __init__(self, step_seconds: float, get_delivery: Callable[[], dict | None], autostart: bool = False):
        self.step = step_seconds
        self.get_delivery = get_delivery
        self.autostart = autostart
        self.eof = False
        self.last_msg_time: float | None = None
        self._run: deque | None = None

    def open(self) -> None:
        total = sum(d for d, _, _ in SCRIPT) * self.step
        log.info("Demo mode: a simulated mission takes about %.0f s.", total)
        if not self.autostart:
            log.info("Waiting for 'Start demo mission' in the app's Warehouse tab (or run with --autostart).")

    def close(self) -> None:
        pass

    @property
    def vehicle_connected(self) -> bool:
        return True

    def describe(self) -> str:
        return "Demo mode (simulated mission)"

    def poll(self, timeout: float) -> DetectedEvent | None:
        now = time.time()
        self.last_msg_time = now
        if self._run is None:
            d = self.get_delivery()
            if d and d.get("status") == "READY" and (self.autostart or d.get("demo_requested")):
                self.autostart = False
                log.info("Starting simulated mission for %s (%s)", d["delivery_id"], d["package_id"])
                t, self._run = now, deque()
                for delay, event, evidence in SCRIPT:
                    t += delay * self.step
                    self._run.append((t, event, evidence))
            else:
                time.sleep(timeout)
                return None
        due, event, evidence = self._run[0]
        if now < due:
            time.sleep(min(timeout, due - now))
            return None
        self._run.popleft()
        if not self._run:
            self._run = None
            log.info("Simulated mission finished. Tap 'Start demo mission' again for another run.")
        return DetectedEvent(event, evidence, time.time(), "DEMO")
