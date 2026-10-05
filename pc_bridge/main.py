"""PC bridge: MAVLink (or demo) -> mission events -> state machine -> SMS + backend API.

Run from the project root, with the virtual environment active:

  python pc_bridge/main.py                      live: listen to the MAVLink copy (MAVLINK_CONNECTION)
  python pc_bridge/main.py --demo               simulated mission, started from the app (Warehouse tab)
  python pc_bridge/main.py --demo --autostart   simulated mission, starts immediately
  python pc_bridge/main.py --replay flight.tlog check detection against a Mission Planner .tlog
                                                (no backend, mock SMS)
  python pc_bridge/main.py --event TAKEOFF      push ONE simulated event through the real pipeline
                                                and exit (step through a mission phase by phase)

The bridge only observes. It never sends anything to the drone.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_client import BackendClient, BackendUnavailable, EventOutbox  # noqa: E402
from config import Settings, load_settings  # noqa: E402
from mission_state import (  # noqa: E402
    TERMINAL, DeliveryState, DetectedEvent, InfoEvent, MissionEvent, MissionStateMachine, Output, StateTransition,
)
from notification_service import MockSMSProvider, NotificationService, SmsLedger, make_provider  # noqa: E402

log = logging.getLogger("bridge")
HOUSEKEEPING_S = 2.0
HEARTBEAT_S = 5.0
ALWAYS_REPEATABLE = {MissionEvent.RTL_STARTED, MissionEvent.HOME_COMPLETED}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Bridge:
    def __init__(self, settings: Settings, source, notifier: NotificationService,
                 client: BackendClient | None, outbox: EventOutbox | None, mode: str):
        self.s, self.source, self.notifier = settings, source, notifier
        self.client, self.outbox, self.mode = client, outbox, mode
        self.offline = client is None
        self.machine = MissionStateMachine()
        self.delivery: dict | None = None  # the bound delivery, including phone numbers
        self.need_delivery = False         # a flight started while no delivery was bound
        # Demo: create one delivery at startup so the app has something to show. Later ones
        # come from "Start demo mission", so a finished delivery stays on screen as COMPLETED.
        self.create_at_startup = mode == "demo"
        self.transitions: list[StateTransition] = []
        self._next_housekeeping = 0.0
        self._next_heartbeat = 0.0
        self._backend_warned = False

    # ------------------------------------------------------------ main loop
    def run(self) -> None:
        self.source.open()
        self._bind_if_possible()
        try:
            while not self.source.eof:
                ev = self.source.poll(0.25)
                if ev is not None:
                    self._on_event(ev)
                self._dispatch(self.machine.tick(self.source.last_msg_time or time.time()))
                self._housekeeping()
        except KeyboardInterrupt:
            log.info("Stopping (Ctrl+C)")
        finally:
            if self.outbox:
                self.outbox.flush(force=True)
            self.source.close()

    def _on_event(self, ev) -> None:
        # Arming in AUTO alone is not a flight: ArduPilot does not restart a mission that has
        # completed until AUTO is re-entered. A delivery is needed only once the drone takes off.
        if not self.machine.bound and ev.event in (MissionEvent.TAKEOFF, MissionEvent.EN_ROUTE,
                                                   MissionEvent.PACKAGE_RELEASED):
            self.need_delivery = True
            self._bind_if_possible()
        repeat = ev.event in self.machine.facts and ev.event not in ALWAYS_REPEATABLE
        outputs = self.machine.handle(ev)
        if repeat and not outputs:
            log.info("Duplicate %s ignored: already recorded, so no new state and no SMS", ev.event.value)
        self._dispatch(outputs)

    def _dispatch(self, outputs: list[Output]) -> None:
        if not outputs:
            return
        transitions = [o for o in outputs if isinstance(o, StateTransition)]
        # 1) Update the backend first, so the app changes right away. This is local and fast.
        if self.outbox:
            for o in outputs:
                is_tr = isinstance(o, StateTransition)
                self.outbox.add(o.delivery_id, {
                    "event_id": o.event_id,
                    "event": o.event.value if is_tr else o.event,
                    "state": o.to_state.value if is_tr else None,
                    "source": o.source,
                    "evidence": o.evidence,
                    "level": "info" if is_tr else o.level,
                    "timestamp": iso(o.timestamp),
                })
            self.outbox.flush(force=True)
        for o in outputs:
            if isinstance(o, InfoEvent):
                log.info("%s %s: %s", "WARNING" if o.level == "warning" else "info", o.event, o.evidence)
        # 2) Then the SMS (customer + warehouse), each deduplicated by the ledger.
        for tr in transitions:
            self.transitions.append(tr)
            self.delivery["status"] = tr.to_state.value
            log.info("══ %s is now %s ══  (%s)", tr.delivery_id, tr.to_state.value, tr.evidence)
            self.notifier.notify(tr, self.delivery)
        if self.machine.bound and self.machine.state in TERMINAL:
            log.info("%s finished as %s. Waiting for the next delivery.", self.machine.delivery_id,
                     self.machine.state.value)
            self.machine.unbind()
            self.delivery, self.need_delivery = None, False

    # ------------------------------------------------------------ backend sync
    def _bind_if_possible(self) -> None:
        if self.machine.bound:
            return
        if self.offline:
            self.delivery = {"delivery_id": "REPLAY-001", "package_id": "PKG-REPLAY", "customer_name": "Replay",
                             "customer_phone": self.s.default_customer_phone or "+10000000001",
                             "warehouse_phone": self.s.warehouse_phone or "+10000000002",
                             "drone_id": self.s.drone_id, "status": "READY"}
        else:
            try:
                d = self.client.get_active_delivery(self.s.drone_id)
                if d is None and (self.need_delivery or self.create_at_startup):
                    d = self.client.create_delivery(
                        customer_name=self.s.default_customer_name, customer_phone=self.s.default_customer_phone or None,
                        warehouse_phone=self.s.warehouse_phone or None, drone_id=self.s.drone_id,
                        source="BRIDGE" if self.mode == "live" else "DEMO")
                    log.info("Created %s for %s using the defaults in .env", d["delivery_id"],
                             "this flight" if self.mode == "live" else "the demo")
            except BackendUnavailable as exc:
                if not self._backend_warned:
                    log.warning("Backend not reachable (%s). Is 'python backend/app.py' running? "
                                "Still watching; events will be applied once it is back.", exc)
                    self._backend_warned = True
                return
            self._backend_warned = False
            self.create_at_startup = False
            if d is None:
                return
            self.delivery = d
        self._dispatch(self.machine.bind(self.delivery["delivery_id"], DeliveryState(self.delivery["status"]),
                                         self.source.last_msg_time or time.time()))

    def _refresh_bound(self) -> None:
        """Pick up operator changes: a cancelled delivery, edited phone numbers, the demo trigger."""
        try:
            d = self.client.get_delivery(self.machine.delivery_id)
        except BackendUnavailable:
            return
        if d is None or (d["status"] in ("COMPLETED", "CANCELLED") and self.machine.state not in TERMINAL):
            log.warning("%s was closed by the warehouse (%s). Detaching.", self.machine.delivery_id,
                        d["status"] if d else "deleted")
            self.machine.unbind()
            self.delivery, self.need_delivery = None, False
            return
        for key in ("package_id", "customer_name", "customer_phone", "warehouse_phone", "demo_requested"):
            self.delivery[key] = d[key]

    def _housekeeping(self) -> None:
        now = time.monotonic()
        if self.offline or now < self._next_housekeeping:
            return
        self._next_housekeeping = now + HOUSEKEEPING_S
        self.outbox.flush()
        self.notifier.retry_failed()
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + HEARTBEAT_S
            try:
                self.client.heartbeat({"drone_id": self.s.drone_id, "mode": self.mode,
                                       "vehicle_connected": self.source.vehicle_connected,
                                       "detail": self.source.describe()})
            except BackendUnavailable:
                pass
        if self.machine.bound:
            self._refresh_bound()
        else:
            self._bind_if_possible()

    # ------------------------------------------------------------ manual stepping
    NEXT_STEP = {
        DeliveryState.READY: "TAKEOFF",
        DeliveryState.DEPARTED: "EN_ROUTE",
        DeliveryState.DELIVERING: "PACKAGE_RELEASED",
        DeliveryState.PACKAGE_DELIVERED: "RTL_STARTED",
        DeliveryState.RETURNING_HOME: "HOME_COMPLETED",
    }

    def run_single(self, event: MissionEvent) -> int:
        """Push ONE simulated event through the real pipeline (state machine, SMS, backend), then exit.

        Each run binds to the active delivery again, so the state stored in the backend carries
        over from the previous command. Repeating an event shows the duplicate protection.
        """
        self.need_delivery = event in (MissionEvent.MISSION_STARTED, MissionEvent.TAKEOFF,
                                       MissionEvent.EN_ROUTE, MissionEvent.PACKAGE_RELEASED)
        self.create_at_startup = False  # only flight-starting events may create a delivery
        self._bind_if_possible()
        if not self.machine.bound:
            print(f"\nNo active delivery to update. Start a new one with:  --event TAKEOFF"
                  f"\n(and check the backend is running at {self.s.api_base_url})\n")
            return 1
        delivery_id, before = self.machine.delivery_id, self.machine.state
        self._on_event(DetectedEvent(event, f"manual test command: {event.value}", time.time(), "DEMO"))
        self.outbox.flush(force=True)
        after = self.transitions[-1].to_state if self.transitions else before
        if self.transitions:
            path = " -> ".join([before.value] + [t.to_state.value for t in self.transitions])
            print(f"\n✔ {delivery_id}: {path}   (check the app now)")
        else:
            print(f"\n• {delivery_id}: still {before.value}. {event.value} caused no state change.")
        hint = self.NEXT_STEP.get(after)
        print(f"  Next phase:  .venv\\Scripts\\python.exe pc_bridge\\main.py --event {hint}\n" if hint
              else "  Delivery finished. Run --event TAKEOFF to start another one.\n")
        return 0

    # ------------------------------------------------------------ replay report
    def print_summary(self) -> None:
        print("\n================ Detected delivery transitions ================")
        if not self.transitions:
            print("  (none) - see the log above for what was received")
        for tr in self.transitions:
            print(f"  {iso(tr.timestamp)}  {tr.from_state.value:>17} -> {tr.to_state.value:<17}  {tr.evidence}")
        print(f"  Final state: {self.machine.state.value if self.machine.state else 'COMPLETED (unbound)'}")
        print("================================================================\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Drone delivery PC bridge (MAVLink observer -> SMS + app API)")
    ap.add_argument("--demo", action="store_true", help="use the simulated DemoEventSource instead of MAVLink")
    ap.add_argument("--autostart", action="store_true", help="with --demo: start the mission immediately")
    ap.add_argument("--connection", help="override MAVLINK_CONNECTION, e.g. udpin:0.0.0.0:14551")
    ap.add_argument("--replay", metavar="TLOG", help="replay a Mission Planner .tlog (no backend, mock SMS)")
    ap.add_argument("--event", type=str.upper, choices=[e.value for e in MissionEvent],
                    help="send ONE simulated mission event through the real pipeline, then exit")
    ap.add_argument("--env", type=Path, help="path to a .env file (default: project root .env)")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):  # emoji in SMS bodies, even when output is redirected
        stream.reconfigure(encoding="utf-8", errors="replace")
    settings = load_settings(args.env)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)-7s %(name)-7s %(message)s",
                        datefmt="%H:%M:%S")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if args.connection:
        settings.mavlink_connection = args.connection

    if args.replay:
        settings.mavlink_connection = args.replay
        provider = MockSMSProvider(settings.data_dir / "replay_sms_outbox.log")
        notifier = NotificationService(provider, SmsLedger(":memory:"), settings.drone_id)
        client = outbox = None
    else:
        provider = make_provider(settings, settings.data_dir)
        db = settings.data_dir / "bridge.db"
        notifier = NotificationService(provider, SmsLedger(db), settings.drone_id)
        client = BackendClient(settings.api_base_url)
        outbox = EventOutbox(db, client)
    log.info("SMS provider: %s | backend: %s", provider.name, "none (replay)" if client is None else settings.api_base_url)

    if args.event:
        if client is None:
            ap.error("--event cannot be combined with --replay")
        single = Bridge(settings, SimpleNamespace(last_msg_time=None), notifier, client, outbox, "demo")
        return single.run_single(MissionEvent(args.event))

    bridge: Bridge
    if args.demo:
        from demo_source import DemoEventSource
        source = DemoEventSource(settings.demo_step_seconds, lambda: bridge.delivery, args.autostart)
    else:
        from mavlink_monitor import MavlinkMonitor
        source = MavlinkMonitor(settings, settings.mission)
    bridge = Bridge(settings, source, notifier, client, outbox, "demo" if args.demo else "live")
    bridge.run()
    if args.replay:
        bridge.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
