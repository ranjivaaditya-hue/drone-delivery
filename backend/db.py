"""SQLite storage: one row per delivery. Its event history is a JSON list.

The schema follows the MVP spec: delivery_id, package_id, customer_name,
customer_phone, warehouse_phone, drone_id, status, timestamp, event_history.
It adds two small housekeeping columns, created_at and demo_requested.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from delivery_states import CANCELLED, FLOW, TERMINAL_STATES, flow_index

SCHEMA = """
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id     TEXT PRIMARY KEY,
    package_id      TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    customer_phone  TEXT NOT NULL,
    warehouse_phone TEXT NOT NULL,
    drone_id        TEXT NOT NULL,
    status          TEXT NOT NULL,
    timestamp       TEXT NOT NULL,              -- time of the latest status change (UTC)
    event_history   TEXT NOT NULL DEFAULT '[]', -- JSON list, oldest first
    created_at      TEXT NOT NULL,
    demo_requested  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deliveries_drone ON deliveries (drone_id, created_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TransitionRejected(Exception):
    """A status change that would move a delivery backwards or out of a terminal state."""


class DeliveryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Writes are read-modify-write on event_history, so serialise them.
        self._write_lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        d["event_history"] = json.loads(d["event_history"] or "[]")
        d["demo_requested"] = bool(d["demo_requested"])
        return d

    # ---------- queries ----------
    def get(self, delivery_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,)).fetchone()
        return self._row(row)

    def latest(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM deliveries ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        return self._row(row)

    def active_for_drone(self, drone_id: str) -> dict | None:
        marks = ",".join("?" * len(TERMINAL_STATES))
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM deliveries WHERE drone_id = ? AND status NOT IN ({marks}) "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (drone_id, *sorted(TERMINAL_STATES)),
            ).fetchone()
        return self._row(row)

    def list(self, statuses: list[str] | None = None, limit: int = 50) -> list[dict]:
        sql, args = "SELECT * FROM deliveries", []
        if statuses:
            sql += f" WHERE status IN ({','.join('?' * len(statuses))})"
            args += statuses
        sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    # ---------- writes ----------
    def create(self, *, customer_name: str, customer_phone: str, warehouse_phone: str,
               drone_id: str, package_id: str | None = None, source: str = "WAREHOUSE") -> dict:
        with self._write_lock, self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] + 1
            while conn.execute("SELECT 1 FROM deliveries WHERE delivery_id = ?", (f"DEL-{n:03d}",)).fetchone():
                n += 1
            delivery_id = f"DEL-{n:03d}"
            now = utc_now()
            history = [{
                "event_id": f"{delivery_id}:READY",
                "event": "ORDER_CONFIRMED",
                "state": "READY",
                "source": source,
                "evidence": "Delivery created",
                "level": "info",
                "timestamp": now,
                "received_at": now,
            }]
            conn.execute(
                "INSERT INTO deliveries (delivery_id, package_id, customer_name, customer_phone, warehouse_phone,"
                " drone_id, status, timestamp, event_history, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (delivery_id, package_id or f"PKG-{n:03d}", customer_name, customer_phone, warehouse_phone,
                 drone_id, "READY", now, json.dumps(history), now),
            )
        return self.get(delivery_id)

    def update_details(self, delivery_id: str, **fields) -> dict | None:
        allowed = {"package_id", "customer_name", "customer_phone", "warehouse_phone"}
        fields = {k: v for k, v in fields.items() if k in allowed and v}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with self._write_lock, self._connect() as conn:
                conn.execute(f"UPDATE deliveries SET {sets} WHERE delivery_id = ?", (*fields.values(), delivery_id))
        return self.get(delivery_id)

    def set_demo_requested(self, delivery_id: str, requested: bool) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute("UPDATE deliveries SET demo_requested = ? WHERE delivery_id = ?",
                         (1 if requested else 0, delivery_id))

    def append_event(self, delivery_id: str, event: dict, new_state: str | None) -> tuple[bool, dict | None]:
        """Add an event to the history and, if new_state is given, change status.

        Idempotent: an event_id that is already in the history is ignored. A state
        that is not ahead of the current one is also ignored. Returns
        (applied, delivery).
        """
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,)).fetchone()
            if row is None:
                return False, None
            history = json.loads(row["event_history"] or "[]")
            if any(e.get("event_id") == event["event_id"] for e in history):
                return False, self._row(row)

            status = row["status"]
            if new_state is not None:
                if status in TERMINAL_STATES:
                    return False, self._row(row)
                if new_state == CANCELLED:
                    pass  # operator may cancel any unfinished delivery
                elif new_state not in FLOW:
                    raise TransitionRejected(f"unknown state {new_state}")
                elif flow_index(new_state) <= flow_index(status):
                    return False, self._row(row)  # duplicate or stale: never move backwards

            now = utc_now()
            history.append({**event, "state": new_state, "received_at": now})
            if new_state is not None:
                conn.execute(
                    "UPDATE deliveries SET status = ?, timestamp = ?, event_history = ?, demo_requested = 0"
                    " WHERE delivery_id = ?",
                    (new_state, event.get("timestamp") or now, json.dumps(history), delivery_id),
                )
            else:
                conn.execute("UPDATE deliveries SET event_history = ? WHERE delivery_id = ?",
                             (json.dumps(history), delivery_id))
        return True, self.get(delivery_id)
