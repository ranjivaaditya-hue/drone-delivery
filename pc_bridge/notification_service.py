"""SMS to the customer and the warehouse, sent when the delivery state changes.

Dedup: each SMS has the key "<delivery_id>:<state>:<role>". The key is claimed
in a SQLite ledger BEFORE sending. A key that is already there is never sent
again, even after the bridge restarts. Sending is at most once per key.
A send that fails is retried, up to 3 attempts in total.

Providers:
  MockSMSProvider    prints the SMS and appends it to data/sms_outbox.log (development)
  TwilioSMSProvider  real SMS. Credentials come only from environment variables.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mission_state import DeliveryState as S, StateTransition

log = logging.getLogger("sms")

CUSTOMER_SMS = {
    S.DEPARTED: "🚁 Your package is on the way!\n\nYour delivery drone has taken off and started its journey.",
    S.PACKAGE_DELIVERED: "📦 Your package has been delivered!\n\n"
                         "The delivery drone has released your package at the delivery location.",
    S.COMPLETED: "🏠 Delivery completed.\n\nThe delivery drone has returned to the warehouse.",
}
WAREHOUSE_SMS = {
    S.DEPARTED: "{drone_id}\n\nDelivery mission started.\n\nPackage: {package_id}\nStatus: DEPARTED",
    S.PACKAGE_DELIVERED: "{drone_id}\n\nPackage {package_id} released at delivery location.\n\nStatus: DELIVERED",
    S.RETURNING_HOME: "{drone_id}\n\nPackage delivery completed.\n\nDrone is returning to warehouse.",
    S.COMPLETED: "{drone_id}\n\nDrone has returned to warehouse.\n\nMission completed.",
}
MAX_ATTEMPTS = 3


@dataclass
class SMSResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


class SMSProvider(ABC):
    name = "base"

    @abstractmethod
    def send(self, to: str, body: str) -> SMSResult:
        ...


class MockSMSProvider(SMSProvider):
    """Development provider: no SMS leaves the PC."""
    name = "mock"

    def __init__(self, outbox_file: Path):
        self.outbox_file = outbox_file
        self._n = 0

    def send(self, to: str, body: str) -> SMSResult:
        self._n += 1
        msg_id = f"MOCK-{int(time.time())}-{self._n}"
        bar = "─" * 46
        print(f"\n┌{bar}\n│ 📱 SMS (mock) to {to}\n├{bar}")
        for line in body.splitlines():
            print(f"│ {line}")
        print(f"└{bar}\n", flush=True)
        self.outbox_file.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": msg_id, "to": to, "body": body,
                                "time": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
        return SMSResult(True, self.name, msg_id)


class TwilioSMSProvider(SMSProvider):
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str = "", messaging_service_sid: str = ""):
        if not account_sid or not auth_token or not (from_number or messaging_service_sid):
            raise ValueError("Twilio needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER "
                             "(or TWILIO_MESSAGING_SERVICE_SID) in .env")
        from twilio.rest import Client  # imported here so the mock setup does not need twilio installed
        self.client = Client(account_sid, auth_token)
        self.from_number, self.messaging_service_sid = from_number, messaging_service_sid

    def send(self, to: str, body: str) -> SMSResult:
        kwargs = {"to": to, "body": body}
        if self.messaging_service_sid:
            kwargs["messaging_service_sid"] = self.messaging_service_sid
        else:
            kwargs["from_"] = self.from_number
        try:
            msg = self.client.messages.create(**kwargs)
            return SMSResult(True, self.name, msg.sid)
        except Exception as exc:  # twilio raises TwilioRestException; network errors vary
            return SMSResult(False, self.name, error=str(exc))


def make_provider(settings, data_dir: Path) -> SMSProvider:
    if settings.sms_provider == "twilio":
        return TwilioSMSProvider(settings.twilio_account_sid, settings.twilio_auth_token,
                                 settings.twilio_from_number, settings.twilio_messaging_service_sid)
    if settings.sms_provider != "mock":
        raise ValueError(f"Unknown SMS_PROVIDER '{settings.sms_provider}' (use mock or twilio)")
    return MockSMSProvider(data_dir / "sms_outbox.log")


class SmsLedger:
    """Remembers every SMS key that was claimed, so nothing is sent twice."""

    def __init__(self, db_path: str | Path):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sms_log (key TEXT PRIMARY KEY, delivery_id TEXT, state TEXT, role TEXT,"
            " phone TEXT, body TEXT, provider TEXT, status TEXT, message_id TEXT, error TEXT,"
            " attempts INTEGER DEFAULT 0, updated_at REAL)")
        self.conn.commit()

    def claim(self, key: str, delivery_id: str, state: str, role: str, phone: str, body: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO sms_log (key, delivery_id, state, role, phone, body, status, updated_at)"
                " VALUES (?,?,?,?,?,?, 'sending', ?)", (key, delivery_id, state, role, phone, body, time.time()))
            self.conn.commit()
            return cur.rowcount == 1

    def record(self, key: str, result: SMSResult) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE sms_log SET status = ?, provider = ?, message_id = ?, error = ?, attempts = attempts + 1,"
                " updated_at = ? WHERE key = ?",
                ("sent" if result.ok else "failed", result.provider, result.message_id, result.error,
                 time.time(), key))
            self.conn.commit()

    def due_retries(self) -> list[tuple]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT key, phone, body, attempts, updated_at FROM sms_log WHERE status = 'failed' AND attempts < ?",
                (MAX_ATTEMPTS,)).fetchall()
        return [r for r in rows if time.time() - r[4] >= 10 * r[3]]  # 10 s, 20 s backoff

    def count(self, delivery_id: str) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM sms_log WHERE delivery_id = ? AND status = 'sent'",
                                     (delivery_id,)).fetchone()[0]


class NotificationService:
    def __init__(self, provider: SMSProvider, ledger: SmsLedger, drone_id: str):
        self.provider, self.ledger, self.drone_id = provider, ledger, drone_id

    def notify(self, tr: StateTransition, delivery: dict) -> None:
        recipients = (("customer", CUSTOMER_SMS, delivery.get("customer_phone")),
                      ("warehouse", WAREHOUSE_SMS, delivery.get("warehouse_phone")))
        for role, templates, phone in recipients:
            template = templates.get(tr.to_state)
            if template is None:
                continue
            if not phone:
                log.warning("No %s phone number for %s, so the %s SMS is skipped", role, tr.delivery_id, tr.to_state.value)
                continue
            body = template.format(drone_id=delivery.get("drone_id") or self.drone_id,
                                   package_id=delivery.get("package_id", ""))
            key = f"{tr.delivery_id}:{tr.to_state.value}:{role}"
            if not self.ledger.claim(key, tr.delivery_id, tr.to_state.value, role, phone, body):
                log.info("SMS %s was already sent, so it is not sent again", key)
                continue
            self._send(key, phone, body)

    def retry_failed(self) -> None:
        for key, phone, body, attempts, _ in self.ledger.due_retries():
            log.info("Retrying SMS %s (attempt %d)", key, attempts + 1)
            self._send(key, phone, body)

    def _send(self, key: str, phone: str, body: str) -> None:
        result = self.provider.send(phone, body)
        self.ledger.record(key, result)
        if result.ok:
            log.info("SMS sent  %-38s -> %s via %s (%s)", key, phone, result.provider, result.message_id)
        else:
            log.error("SMS FAILED %s -> %s via %s: %s", key, phone, result.provider, result.error)
