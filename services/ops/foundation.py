"""SHARED SAFETY & TRANSACTION FOUNDATION for SkyAssist 3.0 operations modules.

Every critical action follows the same pattern:
  read state → check permission → validate rules → check versions → BEGIN IMMEDIATE →
  re-validate inside the transaction → change → append audit event (+ outbox event) → COMMIT → return.

Helpers here are deliberately small and take an open connection `con` so that the audit record,
version bump and outbox event commit (or roll back) together with the change itself.
External calls (n8n) are never made while a write transaction is open: they go through the outbox.
"""
import hashlib
import json
import uuid

from db import query, query_one, tx, utcnow
from services.auth_service import COORDINATOR, PermissionDenied, Principal

SERVICE = "SERVICE"           # authenticated machine identity (n8n / API adapter)
SYSTEM = Principal("system", SERVICE, "SkyAssist system")


class OpsError(Exception):
    """A refused operational action. `code` is machine-readable, the message is human-readable."""

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def require_ops(principal, allow_service=True):
    """OCC actions: coordinators (controllers); some may also be triggered by the service identity."""
    if principal is None:
        raise PermissionDenied("Sign in required.")
    if principal.role == COORDINATOR or (allow_service and principal.role == SERVICE):
        return
    raise PermissionDenied("This operation requires an operations controller.")


def require_controller(principal):
    """Human authorisation only — the service identity (n8n) can never approve."""
    require_ops(principal, allow_service=False)


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- audit (append-only, enforced by trigger)
def audit(con, actor, module, event_type, entity_type=None, entity_id=None, old=None, new=None, txn_id=None,
          reason=None, result=None):
    con.execute("INSERT INTO audit_events(occurred_at,actor,module,event_type,entity_type,entity_id,old_state,"
                "new_state,txn_id,reason,result) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (utcnow(), actor, module, event_type, entity_type, entity_id,
                 json.dumps(old, default=str) if isinstance(old, (dict, list)) else old,
                 json.dumps(new, default=str) if isinstance(new, (dict, list)) else new,
                 txn_id, reason, result))


def audit_now(actor, module, event_type, **kw):
    """Audit in its own small transaction (used to record failures after a rollback)."""
    with tx() as con:
        audit(con, actor, module, event_type, **kw)


# ---------------------------------------------------------------- policies (configurable, auditable)
def policy(key, default=None, as_json=False):
    r = query_one("SELECT value, verified FROM ops_policies WHERE policy_key=?", (key,))
    if not r:
        return default
    return json.loads(r["value"]) if as_json else r["value"]


def policy_row(key):
    return query_one("SELECT * FROM ops_policies WHERE policy_key=?", (key,))


# ---------------------------------------------------------------- idempotency
def idem_lookup(con, key, operation):
    if not key:
        return None
    r = con.execute("SELECT * FROM idempotency_records WHERE idem_key=?", (key,)).fetchone()
    if r is None:
        return None
    if r["operation"] != operation:
        raise OpsError("IDEMPOTENCY_KEY_REUSED", f"Idempotency key already used for {r['operation']}.")
    return json.loads(r["result"])


def idem_store(con, key, operation, request, result):
    if key:
        con.execute("INSERT INTO idempotency_records VALUES(?,?,?,?,?)",
                    (key, operation, canonical_hash(request), json.dumps(result, default=str), utcnow()))


# ---------------------------------------------------------------- versioned resources (optimistic concurrency)
def version_of(con, resource_id):
    r = con.execute("SELECT version FROM resource_versions WHERE resource_id=?", (resource_id,)).fetchone()
    if r is None:
        con.execute("INSERT OR IGNORE INTO resource_versions VALUES(?,1,NULL,?,?)", (resource_id, utcnow(), "INIT"))
        return 1
    return r["version"]


def bump(con, resource_id, state=None, event=None):
    version_of(con, resource_id)
    con.execute("UPDATE resource_versions SET version=version+1, state=?, updated_at=?, last_event=? "
                "WHERE resource_id=?", (json.dumps(state, default=str) if state is not None else None,
                                        utcnow(), event, resource_id))
    return version_of(con, resource_id)


# ---------------------------------------------------------------- outbox (delivered after commit)
def outbox(con, topic, payload):
    con.execute("INSERT INTO workflow_outbox(topic,payload,status,created_at) VALUES(?,?,'PENDING',?)",
                (topic, json.dumps(payload, default=str), utcnow()))


def alert(con, module, severity, entity_id, title, detail=""):
    con.execute("INSERT INTO operational_alerts(module,severity,entity_id,title,detail,status,created_at) "
                "VALUES(?,?,?,?,?,'OPEN',?)", (module, severity, entity_id, title, detail, utcnow()))


def open_alerts(module=None):
    if module:
        return query("SELECT * FROM operational_alerts WHERE status='OPEN' AND module=? ORDER BY alert_id DESC",
                     (module,))
    return query("SELECT * FROM operational_alerts WHERE status='OPEN' ORDER BY alert_id DESC")


def acknowledge_alert(principal, alert_id):
    require_controller(principal)
    with tx() as con:
        cur = con.execute("UPDATE operational_alerts SET status='ACKNOWLEDGED', acknowledged_by=?, acknowledged_at=? "
                          "WHERE alert_id=? AND status='OPEN'", (principal.display_name, utcnow(), alert_id))
        if cur.rowcount:
            audit(con, principal.display_name, "OCC", "ALERT_ACKNOWLEDGED", "alert", str(alert_id))
    return cur.rowcount == 1
