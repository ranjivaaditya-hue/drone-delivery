from mission_state import (
    RTL_BEFORE_RELEASE_GRACE_S, DeliveryState as S, DetectedEvent, InfoEvent, MissionEvent as E,
    MissionStateMachine, StateTransition,
)


def ev(event, t, evidence="test"):
    return DetectedEvent(event, evidence, float(t))


def states(outputs):
    return [o.to_state for o in outputs if isinstance(o, StateTransition)]


def bound_machine(state=S.READY):
    m = MissionStateMachine()
    m.bind("DEL-001", state, 0.0)
    return m


def test_full_mission_walks_every_state_once():
    m = bound_machine()
    seen = []
    for event, t in [(E.MISSION_STARTED, 1), (E.TAKEOFF, 2), (E.EN_ROUTE, 5), (E.DELIVERY_WAYPOINT_REACHED, 20),
                     (E.PACKAGE_RELEASED, 24), (E.RTL_STARTED, 24.2), (E.LANDING, 50), (E.HOME_COMPLETED, 60)]:
        seen += states(m.handle(ev(event, t)))
    assert seen == [S.DEPARTED, S.DELIVERING, S.PACKAGE_DELIVERED, S.RETURNING_HOME, S.COMPLETED]


def test_repeated_release_produces_one_transition():
    m = bound_machine(S.DELIVERING)
    out = [states(m.handle(ev(E.PACKAGE_RELEASED, t))) for t in (30, 30.5, 31)]
    assert out == [[S.PACKAGE_DELIVERED], [], []]


def test_waypoint_reached_never_means_delivered():
    m = bound_machine(S.DELIVERING)
    out = m.handle(ev(E.DELIVERY_WAYPOINT_REACHED, 20))
    assert states(out) == []
    assert m.state is S.DELIVERING
    assert any(isinstance(o, InfoEvent) and o.event == "DELIVERY_WAYPOINT_REACHED" for o in out)


def test_rtl_text_arriving_before_servo_sample_still_orders_states():
    """'Mission: 5 RTL' can arrive ~0.5 s before the SERVO_OUTPUT_RAW sample that shows the drop."""
    m = bound_machine(S.DELIVERING)
    assert states(m.handle(ev(E.RTL_STARTED, 100.0))) == []
    assert states(m.handle(ev(E.PACKAGE_RELEASED, 100.5))) == [S.PACKAGE_DELIVERED, S.RETURNING_HOME]


def test_failsafe_rtl_before_release_is_not_a_delivery():
    m = bound_machine(S.DELIVERING)
    m.handle(ev(E.RTL_STARTED, 100))               # failsafe RTL, package still on board
    warn = m.tick(100 + RTL_BEFORE_RELEASE_GRACE_S + 1)
    assert m.state is S.DELIVERING
    assert warn and warn[0].level == "warning" and warn[0].event == "RTL_BEFORE_RELEASE"
    assert states(m.handle(ev(E.HOME_COMPLETED, 200))) == []   # landed with the package
    assert m.state is S.DELIVERING


def test_mission_resumed_after_failsafe_then_delivered():
    m = bound_machine(S.DELIVERING)
    m.handle(ev(E.RTL_STARTED, 100))                       # failsafe RTL ...
    assert states(m.handle(ev(E.PACKAGE_RELEASED, 300))) == [S.PACKAGE_DELIVERED]  # ... old RTL does not count
    assert states(m.handle(ev(E.RTL_STARTED, 301))) == [S.RETURNING_HOME]
    assert states(m.handle(ev(E.HOME_COMPLETED, 400))) == [S.COMPLETED]


def test_second_flight_forgets_first_flight_landing():
    m = bound_machine(S.DELIVERING)
    m.handle(ev(E.HOME_COMPLETED, 100))                    # aborted first attempt
    m.handle(ev(E.MISSION_STARTED, 200))                   # second attempt
    assert states(m.handle(ev(E.PACKAGE_RELEASED, 300))) == [S.PACKAGE_DELIVERED]
    assert states(m.handle(ev(E.RTL_STARTED, 301))) == [S.RETURNING_HOME]   # not COMPLETED yet
    assert states(m.handle(ev(E.HOME_COMPLETED, 400))) == [S.COMPLETED]


def test_release_first_implies_earlier_states_in_order():
    m = bound_machine()
    out = m.handle(ev(E.PACKAGE_RELEASED, 50))
    assert states(out) == [S.DEPARTED, S.DELIVERING, S.PACKAGE_DELIVERED]
    assert "implied by PACKAGE_RELEASED" in out[0].evidence


def test_events_before_binding_are_applied_on_bind():
    m = MissionStateMachine()
    assert m.handle(ev(E.MISSION_STARTED, 1)) == []
    assert m.handle(ev(E.TAKEOFF, 2)) == []
    out = m.bind("DEL-009", S.READY, 3.0)
    assert states(out) == [S.DEPARTED]
    assert any(isinstance(o, InfoEvent) and o.event == "MISSION_STARTED" for o in out)


def test_rebind_mid_flight_does_not_repeat_states():
    m = MissionStateMachine()
    assert states(m.bind("DEL-001", S.PACKAGE_DELIVERED, 10.0)) == []
    assert states(m.handle(ev(E.TAKEOFF, 11))) == []
    assert states(m.handle(ev(E.PACKAGE_RELEASED, 12))) == []
    assert states(m.handle(ev(E.RTL_STARTED, 13))) == [S.RETURNING_HOME]


def test_terminal_state_ignores_everything():
    m = bound_machine(S.RETURNING_HOME)
    assert states(m.handle(ev(E.HOME_COMPLETED, 5))) == [S.COMPLETED]
    assert states(m.handle(ev(E.HOME_COMPLETED, 6))) == []
    assert m.handle(ev(E.PACKAGE_RELEASED, 7)) == []


def test_transition_event_ids_are_stable():
    m = bound_machine(S.DELIVERING)
    tr = [o for o in m.handle(ev(E.PACKAGE_RELEASED, 1)) if isinstance(o, StateTransition)][0]
    assert tr.event_id == "DEL-001:PACKAGE_DELIVERED"
