"""Outbox dispatcher — delivers committed events to n8n AFTER the database transaction has closed.

* If N8N_WEBHOOK_BASE is set, each event is POSTed to  {base}/{topic-route}  with an HMAC-SHA256 signature
  header (X-SkyAssist-Signature) computed from SKYASSIST_WEBHOOK_SECRET. Secrets are read from the environment
  only and are never logged or written to the database.
* If n8n is not configured, events are marked LOCAL_SIMULATED — the dashboard says so explicitly.
  SkyAssist never reports an external delivery that did not happen.
"""
import hashlib
import hmac
import json
import os

from db import query, tx, utcnow

ROUTES = {  # topic prefix -> n8n workflow webhook path
    "rebooking.": "skyassist/rebooking-events",
    "crew.": "skyassist/crew-events",
    "maintenance.": "skyassist/maintenance-events",
    "approval.": "skyassist/approval-events",
    "gate.": "skyassist/state-change",
    "state.": "skyassist/state-change",
}


def mode():
    return "N8N" if os.environ.get("N8N_WEBHOOK_BASE") else "LOCAL_SIMULATION"


def sign(body: bytes) -> str:
    secret = os.environ.get("SKYASSIST_WEBHOOK_SECRET", "")
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else ""


def route_for(topic):
    for prefix, path in ROUTES.items():
        if topic.startswith(prefix):
            return path
    return "skyassist/misc"


def _claim(limit):
    with tx() as con:
        rows = con.execute("SELECT * FROM workflow_outbox WHERE status IN ('PENDING','RETRY') ORDER BY event_id LIMIT ?",
                           (limit,)).fetchall()
        ids = [r["event_id"] for r in rows]
        for i in ids:
            con.execute("UPDATE workflow_outbox SET status='SENDING', attempts=attempts+1 WHERE event_id=?", (i,))
    return [dict(r) for r in rows]


def _finish(event_id, status, error=None):
    with tx() as con:
        con.execute("UPDATE workflow_outbox SET status=?, sent_at=?, last_error=? WHERE event_id=?",
                    (status, utcnow(), error, event_id))


def dispatch(limit=50, max_attempts=5):
    """Deliver pending events. Network I/O happens here, never inside a write transaction."""
    events = _claim(limit)
    base = os.environ.get("N8N_WEBHOOK_BASE", "").rstrip("/")
    sent = 0
    for e in events:
        if not base:
            _finish(e["event_id"], "LOCAL_SIMULATED")
            continue
        body = json.dumps({"event_id": e["event_id"], "topic": e["topic"], "payload": json.loads(e["payload"])},
                          separators=(",", ":")).encode()  # compact = identical to JS JSON.stringify for n8n HMAC
        try:
            import httpx
            r = httpx.post(f"{base}/{route_for(e['topic'])}", content=body, timeout=5,
                           headers={"Content-Type": "application/json", "X-SkyAssist-Signature": sign(body),
                                    "X-Idempotency-Key": f"outbox-{e['event_id']}"})
            if r.status_code < 300:
                _finish(e["event_id"], "SENT")
                sent += 1
            else:
                _finish(e["event_id"], "RETRY" if e["attempts"] + 1 < max_attempts else "FAILED",
                        f"HTTP {r.status_code}")
        except Exception as ex:  # network error — record type only, never the request/headers
            _finish(e["event_id"], "RETRY" if e["attempts"] + 1 < max_attempts else "FAILED", type(ex).__name__)
    return {"mode": mode(), "processed": len(events), "sent": sent}


def stats():
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM workflow_outbox GROUP BY status")}


def recent(n=30):
    return query("SELECT * FROM workflow_outbox ORDER BY event_id DESC LIMIT ?", (n,))
