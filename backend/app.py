"""Delivery-status API for the Android app (FastAPI + SQLite).

Run from the project root:   python backend/app.py
The phone connects to        http://<this-PC's-LAN-IP>:8000

Only high-level delivery states and events pass through here. Raw MAVLink and
telemetry never leave the PC.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import DeliveryStore, TransitionRejected, utc_now  # noqa: E402
from delivery_states import (  # noqa: E402
    CANCELLED, FLOW, IN_FLIGHT_STATES, STATE_TEXT, TERMINAL_STATES, flow_index,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "backend/data/deliveries.db")
DRONE_ID = os.getenv("DRONE_ID", "DRONE-001")
WAREHOUSE_PHONE = os.getenv("WAREHOUSE_PHONE", "+910000000000")
DEFAULT_CUSTOMER_NAME = os.getenv("DEFAULT_CUSTOMER_NAME", "Demo Customer")
DEFAULT_CUSTOMER_PHONE = os.getenv("DEFAULT_CUSTOMER_PHONE", "+910000000001")
BRIDGE_ONLINE_SECONDS = 15

store = DeliveryStore(DB_PATH)
app = FastAPI(title="Drone Delivery API", version="1.0.0")

# Last heartbeat from the PC bridge, kept in memory only.
_bridge: dict = {"last_seen": None, "mode": None, "vehicle_connected": False, "detail": ""}


# ---------------------------------------------------------------- views
def _event_view(e: dict) -> dict:
    state = e.get("state")
    view = {k: e.get(k) for k in ("event_id", "event", "state", "source", "evidence", "level", "timestamp")}
    if state in STATE_TEXT:
        view["title"] = STATE_TEXT[state]["notification_title"]
        view["body"] = STATE_TEXT[state]["notification_body"]
    return view


def public_view(d: dict | None) -> dict | None:
    """What the Android app sees. Phone numbers are never included."""
    if d is None:
        return None
    text = STATE_TEXT[d["status"]]
    return {
        "delivery_id": d["delivery_id"],
        "package_id": d["package_id"],
        "customer_name": d["customer_name"],
        "drone_id": d["drone_id"],
        "status": d["status"],
        "timestamp": d["timestamp"],
        "created_at": d["created_at"],
        "headline": text["headline"],
        "message": text["message"],
        "summary": text["summary"],
        "notification": {"title": text["notification_title"], "body": text["notification_body"]},
        "is_active": d["status"] not in TERMINAL_STATES,
        "demo_requested": d["demo_requested"],
        "events": [_event_view(e) for e in d["event_history"]],
    }


def bridge_view(d: dict | None) -> dict | None:
    """What the PC bridge sees. It includes phone numbers, because the bridge sends the SMS."""
    return d


def _bridge_status() -> dict:
    seen = _bridge["last_seen"]
    age = None if seen is None else round(time.monotonic() - seen, 1)
    return {
        "online": age is not None and age < BRIDGE_ONLINE_SECONDS,
        "seconds_since_seen": age,
        "mode": _bridge["mode"],
        "vehicle_connected": bool(_bridge["vehicle_connected"]) if age is not None and age < BRIDGE_ONLINE_SECONDS else False,
        "detail": _bridge["detail"],
    }


# ---------------------------------------------------------------- models
class NewDelivery(BaseModel):
    package_id: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    warehouse_phone: str | None = None
    drone_id: str | None = None
    source: str = "WAREHOUSE"


class EventIn(BaseModel):
    event_id: str = Field(..., min_length=3)
    event: str
    state: str | None = None
    source: str = "MAVLINK"
    evidence: str = ""
    level: str = "info"
    timestamp: str | None = None


class BridgeHeartbeat(BaseModel):
    drone_id: str = DRONE_ID
    mode: str  # "live" or "demo"
    vehicle_connected: bool = False
    detail: str = ""


# ---------------------------------------------------------------- app endpoints
@app.get("/api/health")
def health():
    return {"status": "ok", "time": utc_now()}


@app.get("/api/status")
def status():
    return {"server_time": utc_now(), "drone_id": DRONE_ID, "bridge": _bridge_status()}


@app.get("/api/deliveries/current")
def current_delivery():
    """The most recent delivery. It may already be completed. Null if there are none."""
    return {"delivery": public_view(store.latest())}


@app.get("/api/deliveries")
def list_deliveries(status: str | None = Query(None, description="Comma-separated states, e.g. COMPLETED,CANCELLED"),
                    limit: int = Query(50, ge=1, le=500)):
    statuses = [s.strip().upper() for s in status.split(",")] if status else None
    return {"deliveries": [public_view(d) for d in store.list(statuses, limit)]}


@app.get("/api/deliveries/{delivery_id}")
def get_delivery(delivery_id: str):
    d = store.get(delivery_id)
    if d is None:
        raise HTTPException(404, f"Unknown delivery {delivery_id}")
    return {"delivery": public_view(d)}


@app.post("/api/deliveries")
def create_delivery(body: NewDelivery):
    """Prepare the next delivery. If the drone already has a READY delivery, edit that one."""
    drone_id = body.drone_id or DRONE_ID
    active = store.active_for_drone(drone_id)
    if active and active["status"] in IN_FLIGHT_STATES:
        raise HTTPException(409, f"{drone_id} is busy with {active['delivery_id']} ({active['status']}). "
                                 "Cancel it first or wait for it to complete.")
    if active:  # READY: edit it rather than piling up unflown deliveries
        d = store.update_details(active["delivery_id"], package_id=body.package_id,
                                 customer_name=body.customer_name, customer_phone=body.customer_phone,
                                 warehouse_phone=body.warehouse_phone)
    else:
        d = store.create(package_id=body.package_id or None,
                         customer_name=body.customer_name or DEFAULT_CUSTOMER_NAME,
                         customer_phone=body.customer_phone or DEFAULT_CUSTOMER_PHONE,
                         warehouse_phone=body.warehouse_phone or WAREHOUSE_PHONE,
                         drone_id=drone_id, source=body.source)
    return {"delivery": public_view(d)}


@app.post("/api/deliveries/{delivery_id}/cancel")
def cancel_delivery(delivery_id: str):
    """Operator escape hatch for a delivery that can no longer finish normally.

    If the package was already released, the delivery is closed as COMPLETED.
    Otherwise it becomes CANCELLED.
    """
    d = store.get(delivery_id)
    if d is None:
        raise HTTPException(404, f"Unknown delivery {delivery_id}")
    if d["status"] in TERMINAL_STATES:
        raise HTTPException(409, f"{delivery_id} is already {d['status']}")
    delivered = flow_index(d["status"]) >= flow_index("PACKAGE_DELIVERED")
    new_state = "COMPLETED" if delivered else CANCELLED
    event = {
        "event_id": f"{delivery_id}:{new_state}",
        "event": "CLOSED_BY_OPERATOR" if delivered else "CANCELLED_BY_OPERATOR",
        "source": "WAREHOUSE",
        "evidence": f"Closed by the warehouse operator while {d['status']}",
        "level": "warning",
        "timestamp": utc_now(),
    }
    _, d = store.append_event(delivery_id, event, new_state)
    return {"delivery": public_view(d)}


@app.post("/api/demo/start")
def start_demo():
    """Ask the PC bridge, running with --demo, to play a simulated mission."""
    active = store.active_for_drone(DRONE_ID)
    if active and active["status"] != "READY":
        raise HTTPException(409, f"{active['delivery_id']} is already in progress ({active['status']}).")
    if active is None:
        active = store.create(customer_name=DEFAULT_CUSTOMER_NAME, customer_phone=DEFAULT_CUSTOMER_PHONE,
                              warehouse_phone=WAREHOUSE_PHONE, drone_id=DRONE_ID, source="DEMO")
    store.set_demo_requested(active["delivery_id"], True)
    bridge = _bridge_status()
    warning = None
    if not bridge["online"]:
        warning = "The PC bridge is offline. Start it with: python pc_bridge/main.py --demo"
    elif bridge["mode"] != "demo":
        warning = "The PC bridge is in LIVE mode (real MAVLink). Restart it with --demo to simulate."
    return {"delivery": public_view(store.get(active["delivery_id"])), "warning": warning}


@app.get("/api/notifications")
def notifications(limit: int = Query(50, ge=1, le=500)):
    """Customer notification history: every state change, newest first."""
    items = []
    for d in store.list(limit=100):
        for order, e in enumerate(d["event_history"]):
            state = e.get("state")
            if state not in STATE_TEXT:
                continue
            items.append({
                "_order": (e.get("timestamp") or e.get("received_at") or "", d["created_at"], order),
                "id": e["event_id"],
                "delivery_id": d["delivery_id"],
                "package_id": d["package_id"],
                "state": state,
                "title": STATE_TEXT[state]["notification_title"],
                "body": STATE_TEXT[state]["notification_body"],
                "timestamp": e.get("timestamp") or e.get("received_at"),
            })
    items.sort(key=lambda n: n.pop("_order"), reverse=True)  # ties broken by history order
    return {"notifications": items[:limit]}


# ---------------------------------------------------------------- bridge endpoints
@app.get("/api/drones/{drone_id}/active-delivery")
def active_delivery(drone_id: str):
    return {"delivery": bridge_view(store.active_for_drone(drone_id))}


@app.get("/api/bridge/deliveries/{delivery_id}")
def bridge_get_delivery(delivery_id: str):
    d = store.get(delivery_id)
    if d is None:
        raise HTTPException(404, f"Unknown delivery {delivery_id}")
    return {"delivery": bridge_view(d)}


@app.post("/api/deliveries/{delivery_id}/events")
def post_event(delivery_id: str, body: EventIn):
    """Record a delivery event from the PC bridge. Idempotent by event_id."""
    if body.state is not None and body.state not in FLOW:
        raise HTTPException(422, f"state must be one of {FLOW} or null")
    event = body.model_dump(exclude={"state"})
    event["timestamp"] = body.timestamp or utc_now()
    try:
        applied, d = store.append_event(delivery_id, event, body.state)
    except TransitionRejected as exc:
        raise HTTPException(422, str(exc))
    if d is None:
        raise HTTPException(404, f"Unknown delivery {delivery_id}")
    return {"applied": applied, "delivery": bridge_view(d)}


@app.post("/api/bridge/heartbeat")
def bridge_heartbeat(body: BridgeHeartbeat):
    _bridge.update(last_seen=time.monotonic(), mode=body.mode,
                   vehicle_connected=body.vehicle_connected, detail=body.detail)
    return {"ok": True}


# ---------------------------------------------------------------- entry point
def lan_addresses() -> list[str]:
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outbound interface
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


if __name__ == "__main__":
    import uvicorn

    print(f"Database: {DB_PATH}")
    print("Enter one of these in the app (Settings > Server URL):")
    for ip in lan_addresses() or ["<this-PC-IP>"]:
        print(f"    http://{ip}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
