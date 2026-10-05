"""Talks to the FastAPI backend. Only high-level delivery events are sent, never MAVLink.

Events go through a small persistent outbox (SQLite). If the backend is down
or restarting, nothing is lost: events are re-sent in order once it is back.
That is safe because the backend ignores an event_id it has already stored.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger("api")


class BackendUnavailable(Exception):
    pass


class BackendClient:
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            r = self.session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise BackendUnavailable(f"{self.base_url} unreachable: {exc.__class__.__name__}") from exc
        if r.status_code >= 500:
            raise BackendUnavailable(f"{method} {path} -> HTTP {r.status_code}")
        if r.status_code >= 400:
            raise ValueError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def get_active_delivery(self, drone_id: str) -> dict | None:
        return self._call("GET", f"/api/drones/{drone_id}/active-delivery")["delivery"]

    def get_delivery(self, delivery_id: str) -> dict | None:
        return self._call("GET", f"/api/bridge/deliveries/{delivery_id}")["delivery"]

    def create_delivery(self, **fields) -> dict:
        public = self._call("POST", "/api/deliveries", json=fields)["delivery"]
        return self.get_delivery(public["delivery_id"])

    def post_event(self, delivery_id: str, payload: dict) -> dict:
        return self._call("POST", f"/api/deliveries/{delivery_id}/events", json=payload)

    def heartbeat(self, payload: dict) -> None:
        self._call("POST", "/api/bridge/heartbeat", json=payload)


class EventOutbox:
    def __init__(self, db_path: str | Path, client: BackendClient):
        self.client = client
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                          " delivery_id TEXT, payload TEXT, created REAL)")
        self.conn.commit()
        self._backoff_until = 0.0

    def add(self, delivery_id: str, payload: dict) -> None:
        with self._lock:
            self.conn.execute("INSERT INTO outbox (delivery_id, payload, created) VALUES (?,?,?)",
                              (delivery_id, json.dumps(payload), time.time()))
            self.conn.commit()

    def pending(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def flush(self, force: bool = False) -> None:
        """Send queued events in order. Stops at the first network failure."""
        if not force and time.monotonic() < self._backoff_until:
            return
        while True:
            with self._lock:
                row = self.conn.execute("SELECT id, delivery_id, payload FROM outbox ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return
            row_id, delivery_id, payload = row
            try:
                result = self.client.post_event(delivery_id, json.loads(payload))
                event = json.loads(payload)
                if result.get("applied"):
                    log.info("Backend updated: %s %s", delivery_id, event.get("state") or event.get("event"))
                else:
                    log.info("Backend already had %s (ignored as a duplicate)", event["event_id"])
            except BackendUnavailable as exc:
                self._backoff_until = time.monotonic() + 3.0
                log.warning("Backend unavailable, %d event(s) queued: %s", self.pending(), exc)
                return
            except ValueError as exc:  # 4xx: the backend rejected this event, so retrying will not help
                log.error("Backend rejected event, dropping it: %s", exc)
            with self._lock:
                self.conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
                self.conn.commit()
