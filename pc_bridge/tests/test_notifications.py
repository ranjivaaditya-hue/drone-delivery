from mission_state import DeliveryState as S, MissionEvent as E, StateTransition
from notification_service import NotificationService, SMSProvider, SMSResult, SmsLedger

DELIVERY = {"delivery_id": "DEL-001", "package_id": "PKG-001", "drone_id": "DRONE-001",
            "customer_phone": "+910000000001", "warehouse_phone": "+910000000002"}


class RecordingProvider(SMSProvider):
    name = "recording"

    def __init__(self, fail_first=0):
        self.sent, self.fail_first = [], fail_first

    def send(self, to, body):
        if self.fail_first:
            self.fail_first -= 1
            return SMSResult(False, self.name, error="network down")
        self.sent.append((to, body))
        return SMSResult(True, self.name, f"id{len(self.sent)}")


def tr(state):
    return StateTransition("DEL-001", S.READY, state, E.TAKEOFF, "test", "MAVLINK", 0.0)


def full_run(service):
    for state in (S.DEPARTED, S.DELIVERING, S.PACKAGE_DELIVERED, S.RETURNING_HOME, S.COMPLETED):
        service.notify(tr(state), DELIVERY)


def test_full_mission_sms_counts_and_text():
    p = RecordingProvider()
    full_run(NotificationService(p, SmsLedger(":memory:"), "DRONE-001"))
    customer = [b for to, b in p.sent if to == "+910000000001"]
    warehouse = [b for to, b in p.sent if to == "+910000000002"]
    assert len(customer) == 3 and len(warehouse) == 4
    assert customer[0].startswith("🚁 Your package is on the way!")
    assert customer[1].startswith("📦 Your package has been delivered!")
    assert customer[2].startswith("🏠 Delivery completed.")
    assert warehouse[0] == "DRONE-001\n\nDelivery mission started.\n\nPackage: PKG-001\nStatus: DEPARTED"
    assert warehouse[1] == "DRONE-001\n\nPackage PKG-001 released at delivery location.\n\nStatus: DELIVERED"
    assert warehouse[2] == "DRONE-001\n\nPackage delivery completed.\n\nDrone is returning to warehouse."
    assert warehouse[3] == "DRONE-001\n\nDrone has returned to warehouse.\n\nMission completed."


def test_same_state_three_times_sends_one_sms_each(tmp_path):
    p = RecordingProvider()
    svc = NotificationService(p, SmsLedger(tmp_path / "bridge.db"), "DRONE-001")
    for _ in range(3):
        svc.notify(tr(S.PACKAGE_DELIVERED), DELIVERY)
    assert len(p.sent) == 2  # one customer + one warehouse


def test_ledger_survives_bridge_restart(tmp_path):
    db = tmp_path / "bridge.db"
    p1 = RecordingProvider()
    NotificationService(p1, SmsLedger(db), "DRONE-001").notify(tr(S.DEPARTED), DELIVERY)
    p2 = RecordingProvider()  # "restarted" bridge
    NotificationService(p2, SmsLedger(db), "DRONE-001").notify(tr(S.DEPARTED), DELIVERY)
    assert len(p1.sent) == 2 and p2.sent == []


def test_failed_sms_is_retried_not_duplicated(tmp_path, monkeypatch):
    import notification_service
    p = RecordingProvider(fail_first=1)
    ledger = SmsLedger(tmp_path / "bridge.db")
    svc = NotificationService(p, ledger, "DRONE-001")
    svc.notify(tr(S.PACKAGE_DELIVERED), DELIVERY)
    assert len(p.sent) == 1  # customer SMS failed, warehouse SMS sent
    now = notification_service.time.time()
    monkeypatch.setattr(notification_service.time, "time", lambda: now + 60)
    svc.retry_failed()
    svc.retry_failed()
    assert len(p.sent) == 2
