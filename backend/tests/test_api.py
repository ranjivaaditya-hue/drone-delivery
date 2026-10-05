import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def client(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "test.db")
    os.environ["WAREHOUSE_PHONE"] = "+910000000002"
    import app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.app)


def ev(delivery_id, state, event="X", **kw):
    return {"event_id": f"{delivery_id}:{state or event}", "event": event, "state": state,
            "source": "MAVLINK", "evidence": "test", **kw}


def test_full_flow_and_idempotency(client):
    d = client.post("/api/deliveries", json={"customer_name": "Asha", "customer_phone": "+910000000001"}).json()["delivery"]
    did = d["delivery_id"]
    assert d["status"] == "READY" and d["package_id"] == "PKG-001"
    assert "customer_phone" not in d  # app view never exposes phone numbers

    for state in ["DEPARTED", "DELIVERING", "PACKAGE_DELIVERED", "RETURNING_HOME", "COMPLETED"]:
        r = client.post(f"/api/deliveries/{did}/events", json=ev(did, state)).json()
        assert r["applied"] and r["delivery"]["status"] == state

    again = client.post(f"/api/deliveries/{did}/events", json=ev(did, "PACKAGE_DELIVERED")).json()
    assert again["applied"] is False and again["delivery"]["status"] == "COMPLETED"

    cur = client.get("/api/deliveries/current").json()["delivery"]
    assert cur["status"] == "COMPLETED" and cur["is_active"] is False
    assert cur["headline"] == "DELIVERY COMPLETED"
    notes = client.get("/api/notifications").json()["notifications"]
    assert [n["state"] for n in notes][:3] == ["COMPLETED", "RETURNING_HOME", "PACKAGE_DELIVERED"]
    hist = client.get("/api/deliveries", params={"status": "COMPLETED,CANCELLED"}).json()["deliveries"]
    assert [h["delivery_id"] for h in hist] == [did]


def test_state_never_moves_backwards(client):
    did = client.post("/api/deliveries", json={}).json()["delivery"]["delivery_id"]
    client.post(f"/api/deliveries/{did}/events", json=ev(did, "PACKAGE_DELIVERED"))
    r = client.post(f"/api/deliveries/{did}/events", json=ev(did, "DEPARTED")).json()
    assert r["applied"] is False and r["delivery"]["status"] == "PACKAGE_DELIVERED"


def test_info_events_do_not_change_state(client):
    did = client.post("/api/deliveries", json={}).json()["delivery"]["delivery_id"]
    r = client.post(f"/api/deliveries/{did}/events",
                    json=ev(did, None, event="DELIVERY_WAYPOINT_REACHED")).json()
    assert r["applied"] and r["delivery"]["status"] == "READY"


def test_ready_delivery_is_edited_not_duplicated(client):
    a = client.post("/api/deliveries", json={"customer_name": "A"}).json()["delivery"]
    b = client.post("/api/deliveries", json={"customer_name": "B", "package_id": "PKG-77"}).json()["delivery"]
    assert a["delivery_id"] == b["delivery_id"] and b["customer_name"] == "B" and b["package_id"] == "PKG-77"


def test_busy_drone_rejects_new_delivery_and_cancel_works(client):
    did = client.post("/api/deliveries", json={}).json()["delivery"]["delivery_id"]
    client.post(f"/api/deliveries/{did}/events", json=ev(did, "DELIVERING"))
    assert client.post("/api/deliveries", json={}).status_code == 409
    c = client.post(f"/api/deliveries/{did}/cancel").json()["delivery"]
    assert c["status"] == "CANCELLED"
    late = client.post(f"/api/deliveries/{did}/events", json=ev(did, "PACKAGE_DELIVERED")).json()
    assert late["applied"] is False  # a cancelled delivery stays cancelled
    nxt = client.post("/api/deliveries", json={}).json()["delivery"]
    assert nxt["delivery_id"] == "DEL-002"


def test_cancel_after_release_closes_as_completed(client):
    did = client.post("/api/deliveries", json={}).json()["delivery"]["delivery_id"]
    client.post(f"/api/deliveries/{did}/events", json=ev(did, "PACKAGE_DELIVERED"))
    assert client.post(f"/api/deliveries/{did}/cancel").json()["delivery"]["status"] == "COMPLETED"


def test_demo_start_and_bridge_status(client):
    r = client.post("/api/demo/start").json()
    assert r["delivery"]["demo_requested"] is True
    assert "offline" in r["warning"]
    client.post("/api/bridge/heartbeat", json={"mode": "demo", "vehicle_connected": True})
    st = client.get("/api/status").json()["bridge"]
    assert st["online"] and st["mode"] == "demo"
    bridge_view = client.get("/api/drones/DRONE-001/active-delivery").json()["delivery"]
    assert bridge_view["warehouse_phone"] == "+910000000002"  # the bridge does get phone numbers
