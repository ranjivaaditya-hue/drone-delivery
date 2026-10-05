"""Delivery state machine: detected mission events -> delivery state transitions.

Guarantees, which are what keeps SMS from being repeated:
  * Each detected event sets a latched fact. Seeing the same event again changes nothing.
  * The delivery state is computed from the facts and only ever moves forward.
  * Each state is entered at most once per delivery, so it causes at most one
    notification per state. The SMS ledger and the backend's idempotent event
    ids are two more layers on top of this.
  * Evidence may arrive out of order. For example, the "Mission: 5 RTL" text can
    arrive before the next SERVO_OUTPUT_RAW sample that shows the release. The
    state still walks through every intermediate state, in order.

The package is marked delivered ONLY on PACKAGE_RELEASED (servo evidence).
Reaching the delivery waypoint never counts as delivered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger("state")


class DeliveryState(str, Enum):
    READY = "READY"
    DEPARTED = "DEPARTED"
    DELIVERING = "DELIVERING"
    PACKAGE_DELIVERED = "PACKAGE_DELIVERED"
    RETURNING_HOME = "RETURNING_HOME"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"  # set only by the warehouse operator

    @property
    def index(self) -> int:
        return FLOW.index(self) if self in FLOW else len(FLOW)


FLOW = [DeliveryState.READY, DeliveryState.DEPARTED, DeliveryState.DELIVERING,
        DeliveryState.PACKAGE_DELIVERED, DeliveryState.RETURNING_HOME, DeliveryState.COMPLETED]
TERMINAL = {DeliveryState.COMPLETED, DeliveryState.CANCELLED}


class MissionEvent(str, Enum):
    MISSION_STARTED = "MISSION_STARTED"                      # armed in AUTO               (info)
    TAKEOFF = "TAKEOFF"                                      # airborne on the mission     -> DEPARTED
    EN_ROUTE = "EN_ROUTE"                                    # takeoff item done, flying   -> DELIVERING
    DELIVERY_WAYPOINT_REACHED = "DELIVERY_WAYPOINT_REACHED"  # info only, never "delivered"
    PACKAGE_RELEASED = "PACKAGE_RELEASED"                    # servo release               -> PACKAGE_DELIVERED
    RTL_STARTED = "RTL_STARTED"                              # return leg                  -> RETURNING_HOME
    LANDING = "LANDING"                                      # (info)
    HOME_COMPLETED = "HOME_COMPLETED"                        # disarmed after the flight   -> COMPLETED


@dataclass(frozen=True)
class DetectedEvent:
    event: MissionEvent
    evidence: str
    timestamp: float          # unix seconds (message receive time, or log time on replay)
    source: str = "MAVLINK"   # MAVLINK | DEMO | BACKEND


@dataclass(frozen=True)
class StateTransition:
    delivery_id: str
    from_state: DeliveryState
    to_state: DeliveryState
    event: MissionEvent
    evidence: str
    source: str
    timestamp: float

    @property
    def event_id(self) -> str:
        return f"{self.delivery_id}:{self.to_state.value}"


@dataclass(frozen=True)
class InfoEvent:
    """Operator-log entry that does not change the delivery state."""
    delivery_id: str
    event: str
    evidence: str
    source: str
    timestamp: float
    level: str = "info"

    @property
    def event_id(self) -> str:
        return f"{self.delivery_id}:{self.event}:{int(self.timestamp * 1000)}"


Output = StateTransition | InfoEvent

# Facts that a stored state implies. Used when the bridge re-binds to a delivery mid-flight.
_IMPLIED = {
    DeliveryState.DEPARTED: [MissionEvent.TAKEOFF],
    DeliveryState.DELIVERING: [MissionEvent.TAKEOFF, MissionEvent.EN_ROUTE],
    DeliveryState.PACKAGE_DELIVERED: [MissionEvent.TAKEOFF, MissionEvent.EN_ROUTE, MissionEvent.PACKAGE_RELEASED],
    DeliveryState.RETURNING_HOME: [MissionEvent.TAKEOFF, MissionEvent.EN_ROUTE, MissionEvent.PACKAGE_RELEASED,
                                   MissionEvent.RTL_STARTED],
}
# An RTL may be reported up to this many seconds before the release evidence arrives
# and still count as "returning after the release". This covers out-of-order arrival
# on a slow link. An RTL earlier than that, such as a failsafe RTL before the drop,
# is not a post-delivery return.
RTL_BEFORE_RELEASE_GRACE_S = 15.0
_INFO_EVENTS = {MissionEvent.MISSION_STARTED, MissionEvent.DELIVERY_WAYPOINT_REACHED, MissionEvent.LANDING}
# Which fact moves the delivery into each state.
_CAUSE = {
    DeliveryState.DEPARTED: MissionEvent.TAKEOFF,
    DeliveryState.DELIVERING: MissionEvent.EN_ROUTE,
    DeliveryState.PACKAGE_DELIVERED: MissionEvent.PACKAGE_RELEASED,
    DeliveryState.RETURNING_HOME: MissionEvent.RTL_STARTED,
    DeliveryState.COMPLETED: MissionEvent.HOME_COMPLETED,
}


class MissionStateMachine:
    def __init__(self) -> None:
        self.delivery_id: str | None = None
        self.state: DeliveryState | None = None
        self._reset_facts()

    def _reset_facts(self) -> None:
        # Delivery-scoped facts: once true, they stay true for this delivery.
        self.facts: dict[MissionEvent, DetectedEvent] = {}
        # Flight-scoped facts: cleared when a new flight starts after one has ended.
        self.rtl_events: list[DetectedEvent] = []
        self.home_completed: DetectedEvent | None = None
        self._pending_info: list[DetectedEvent] = []
        self._warned: set[str] = set()

    @property
    def bound(self) -> bool:
        return self.delivery_id is not None

    # ------------------------------------------------------------ binding
    def bind(self, delivery_id: str, stored_state: DeliveryState, now: float) -> list[Output]:
        """Attach to the backend's active delivery.

        Facts gathered while unbound are kept, so nothing seen before the
        delivery existed is lost. Facts implied by the stored state are added.
        Then the state catches up to whatever the facts support.
        """
        if self.delivery_id != delivery_id:
            log.info("Bound to %s (stored state %s)", delivery_id, stored_state.value)
        self.delivery_id, self.state = delivery_id, stored_state
        for ev in _IMPLIED.get(stored_state, []):
            restored = DetectedEvent(ev, f"restored: delivery was already {stored_state.value}", now, "BACKEND")
            if ev is MissionEvent.RTL_STARTED:
                if not self.rtl_events:
                    self.rtl_events.append(restored)
            else:
                self.facts.setdefault(ev, restored)
        out: list[Output] = [self._info(ev) for ev in self._pending_info]
        self._pending_info.clear()
        return out + self._advance()

    def unbind(self) -> None:
        log.info("Unbound from %s (%s)", self.delivery_id, self.state.value if self.state else None)
        self.delivery_id, self.state = None, None
        self._reset_facts()

    # ------------------------------------------------------------ events
    def handle(self, ev: DetectedEvent) -> list[Output]:
        out: list[Output] = []
        e = ev.event
        if e is MissionEvent.MISSION_STARTED and self.home_completed is not None:
            # A new flight after a finished one: forget the old flight's return and landing.
            self.rtl_events.clear()
            self.home_completed = None

        if e is MissionEvent.RTL_STARTED:
            self.rtl_events.append(ev)
        elif e is MissionEvent.HOME_COMPLETED:
            if self.home_completed is None:
                self.home_completed = ev
            if MissionEvent.PACKAGE_RELEASED not in self.facts:
                out += self._warn_once("FLIGHT_ENDED_WITHOUT_RELEASE", ev,
                                       "Drone disarmed, but no package release was detected on this flight. "
                                       "Check the package, then close or cancel the delivery in Warehouse mode.")
        else:
            if e in _INFO_EVENTS and e not in self.facts:
                if self.bound:
                    out.append(self._info(ev))
                else:
                    self._pending_info.append(ev)
            self.facts.setdefault(e, ev)  # latched: the first evidence wins, repeats change nothing
        return out + self._advance()

    def tick(self, now: float) -> list[Output]:
        """Time-based checks. Called regularly with the current (or log-replay) time."""
        if (self.rtl_events and MissionEvent.PACKAGE_RELEASED not in self.facts
                and now - self.rtl_events[-1].timestamp > RTL_BEFORE_RELEASE_GRACE_S):
            return self._warn_once("RTL_BEFORE_RELEASE", self.rtl_events[-1],
                                   "Drone is returning, but no package release was detected. "
                                   "The customer has NOT been told the package was delivered.")
        return []

    # ------------------------------------------------------------ derivation
    def _returning(self) -> DetectedEvent | None:
        released = self.facts.get(MissionEvent.PACKAGE_RELEASED)
        if released is None:
            return None
        for rtl in self.rtl_events:
            if rtl.timestamp >= released.timestamp - RTL_BEFORE_RELEASE_GRACE_S:
                return rtl
        return None

    def target_state(self) -> DeliveryState:
        f = self.facts
        if MissionEvent.PACKAGE_RELEASED in f:
            rtl = self._returning()
            if rtl is None:
                return DeliveryState.PACKAGE_DELIVERED
            if self.home_completed is not None and self.home_completed.timestamp >= rtl.timestamp:
                return DeliveryState.COMPLETED
            return DeliveryState.RETURNING_HOME
        if MissionEvent.EN_ROUTE in f:
            return DeliveryState.DELIVERING
        if MissionEvent.TAKEOFF in f:
            return DeliveryState.DEPARTED
        return DeliveryState.READY

    def _evidence_for(self, state: DeliveryState) -> DetectedEvent | None:
        cause = _CAUSE[state]
        if cause is MissionEvent.RTL_STARTED:
            return self._returning()
        if cause is MissionEvent.HOME_COMPLETED:
            return self.home_completed
        return self.facts.get(cause)

    def _advance(self) -> list[Output]:
        if not self.bound or self.state in TERMINAL:
            return []
        target = self.target_state()
        out: list[Output] = []
        while self.state.index < target.index:
            nxt = FLOW[self.state.index + 1]
            ev = self._evidence_for(nxt)
            if ev is not None:
                evidence = ev.evidence
            else:
                # No direct evidence for this step: a later fact implies it.
                # Example: the release was seen but the takeoff sample was lost.
                ev = self._evidence_for(target)
                evidence = f"implied by {ev.event.value}: {ev.evidence}"
            out.append(StateTransition(self.delivery_id, self.state, nxt, _CAUSE[nxt], evidence,
                                       ev.source, ev.timestamp))
            log.info("%s: %s -> %s  [%s]", self.delivery_id, self.state.value, nxt.value, evidence)
            self.state = nxt
        return out

    def _info(self, ev: DetectedEvent) -> InfoEvent:
        return InfoEvent(self.delivery_id, ev.event.value, ev.evidence, ev.source, ev.timestamp)

    def _warn_once(self, key: str, ev: DetectedEvent, text: str) -> list[Output]:
        if not self.bound or key in self._warned:
            return []
        self._warned.add(key)
        log.warning("%s: %s", self.delivery_id, text)
        return [InfoEvent(self.delivery_id, key, f"{text} [{ev.evidence}]", ev.source, ev.timestamp, "warning")]
