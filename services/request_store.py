"""DURABLE ASSISTANCE-REQUEST LIFECYCLE (SQLite is the source of truth).

Decision states:  PENDING → APPROVED | DECLINED            (status column)
Dispatch states:  NONE → ASSIGNED → DISPATCHED → EN_ROUTE → COMPLETED   (dispatch_status column)
Escalation:       escalated_at is stamped when a PENDING request waits too long. It is NEVER an approval.

Every transition is a single atomic UPDATE guarded by the expected current state inside
BEGIN IMMEDIATE, so two coordinators can never both decide the same request.
"""
import json
import uuid

from db import query, query_one, tx, utcnow

ESCALATE_AFTER_S = 90
MAX_GATE_HOLD_MIN = 10

ACTION_TEXT = {
    "WHEELCHAIR_AT_DOOR": "wheelchair at the aircraft door",
    "MOBILITY_CART": "priority mobility cart",
    "STAFF_ESCORT": "staff escort from the aircraft to the gate",
    "GATE_HOLD_UP_TO_10_MIN": f"short gate hold (up to {MAX_GATE_HOLD_MIN} min)",
    "ESCORT_TO_TRANSFER_DESK": "staff escort to the Transfer Desk",
}
DISPATCH_FLOW = ["NONE", "ASSIGNED", "DISPATCHED", "EN_ROUTE", "COMPLETED"]


class StateConflict(Exception):
    """The request is no longer in the state this action expects (e.g. already decided)."""


def _event(con, request_id, event_type, actor, detail=None):
    con.execute("INSERT INTO request_events(request_id,event_type,actor,detail,created_at) VALUES(?,?,?,?,?)",
                (request_id, event_type, actor, json.dumps(detail, default=str) if detail is not None else None,
                 utcnow()))


def notify(con, booking_ref, request_id, kind, message):
    con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) VALUES(?,?,?,?,?)",
                (booking_ref, request_id, kind, message, utcnow()))
    _event(con, request_id, "PASSENGER_NOTIFIED", "system", {"kind": kind})


def describe(actions):
    return ", ".join(ACTION_TEXT.get(a, a) for a in actions)


# ------------------------------------------------------------------ create (idempotent per booking)
def active_request(booking_ref, con=None):
    sql = ("SELECT * FROM dispatch_requests WHERE booking_ref=? AND (status='PENDING' OR "
           "(status='APPROVED' AND dispatch_status!='COMPLETED')) ORDER BY created_at DESC LIMIT 1")
    if con is not None:
        r = con.execute(sql, (booking_ref,)).fetchone()
        return dict(r) if r else None
    return query_one(sql, (booking_ref,))


def create_request(conv_id, booking_ref, actions, reason, context, source="AGENT", actor="agent"):
    """Returns (request_id, created). If the booking already has an active request, it is reused
    instead of creating a duplicate."""
    with tx() as con:
        if booking_ref:
            existing = active_request(booking_ref, con)
            if existing:
                return existing["id"], False
        req_id = "REQ-" + uuid.uuid4().hex[:6].upper()
        now = utcnow()
        con.execute(
            "INSERT INTO dispatch_requests(id,conv_id,booking_ref,actions,reason,context,status,created_at_utc,"
            "updated_at_utc,dispatch_status,source) VALUES(?,?,?,?,?,?,'PENDING',?,?,'NONE',?)",
            (req_id, conv_id, booking_ref, json.dumps(actions), reason, json.dumps(context), now, now, source))
        _event(con, req_id, "REQUEST_CREATED", actor, {"actions": actions, "reason": reason, "source": source})
        _event(con, req_id, "COORDINATOR_NOTIFIED", "system", {"channel": "coordinator queue"})
        if booking_ref:
            notify(con, booking_ref, req_id, "REQUESTED",
                   f"Your request for {describe(actions)} has been submitted. Waiting for airport coordinator "
                   f"approval. It has not been confirmed yet, and no staff dispatch has been confirmed.")
        return req_id, True


# ------------------------------------------------------------------ decide (atomic, exactly once)
def decide(request_id, approved: bool, coordinator: str, note: str = "", hold_minutes=None,
           staff_id=None, resource_id=None):
    note = (note or "").strip()
    with tx() as con:
        req = con.execute("SELECT * FROM dispatch_requests WHERE id=?", (request_id,)).fetchone()
        if not req:
            raise StateConflict(f"{request_id} does not exist.")
        actions = json.loads(req["actions"])
        hold = 0
        if approved and "GATE_HOLD_UP_TO_10_MIN" in actions:
            hold = MAX_GATE_HOLD_MIN if hold_minutes is None else int(hold_minutes)
            if not 0 <= hold <= MAX_GATE_HOLD_MIN:
                raise ValueError(f"Gate hold must be between 0 and {MAX_GATE_HOLD_MIN} minutes.")
        now = utcnow()
        cur = con.execute(
            "UPDATE dispatch_requests SET status=?, resolved_by=?, note=?, resolved_at=strftime('%s','now'), "
            "resolved_at_utc=?, updated_at_utc=?, hold_minutes_approved=? WHERE id=? AND status='PENDING'",
            ("APPROVED" if approved else "DECLINED", coordinator, note, now, now, hold, request_id))
        if cur.rowcount != 1:
            raise StateConflict(f"{request_id} was already {req['status'].lower()} by {req['resolved_by']}.")
        _event(con, request_id, "APPROVED" if approved else "DECLINED", coordinator,
               {"note": note, "hold_minutes": hold})
        if approved and (staff_id or resource_id):
            _assign(con, request_id, coordinator, staff_id, resource_id)
        if req["booking_ref"]:
            if approved:
                msg = f"Your request was approved by {coordinator}. Approved: {describe(actions)}."
                if hold:
                    msg += f" Gate hold approved for up to {hold} min."
                if note:
                    msg += f" Note: {note.rstrip('.')}."
                msg += " Staff dispatch has not been confirmed yet; you will see it here when it is."
                notify(con, req["booking_ref"], request_id, "APPROVED", msg)
            else:
                notify(con, req["booking_ref"], request_id, "DECLINED",
                       f"Your assistance request was not approved by {coordinator}"
                       f"{' (' + note + ')' if note else ''}. No staff are on the way. Please go to the "
                       f"nearest Transfer Desk, or ask cabin crew at the aircraft door for help.")
    return get(request_id)


# ------------------------------------------------------------------ dispatch lifecycle
def _assign(con, request_id, actor, staff_id, resource_id):
    if staff_id:
        r = con.execute("UPDATE staff SET status='ASSIGNED' WHERE staff_id=? AND status='AVAILABLE'", (staff_id,))
        if r.rowcount != 1:
            raise StateConflict(f"Staff {staff_id} is not available.")
    if resource_id:
        r = con.execute("UPDATE mobility_resources SET status='ASSIGNED' WHERE resource_id=? AND status='AVAILABLE'",
                        (resource_id,))
        if r.rowcount != 1:
            raise StateConflict(f"Resource {resource_id} is not available.")
    cur = con.execute(
        "UPDATE dispatch_requests SET assigned_staff_id=COALESCE(?,assigned_staff_id), "
        "assigned_resource_id=COALESCE(?,assigned_resource_id), dispatch_status='ASSIGNED', updated_at_utc=? "
        "WHERE id=? AND status='APPROVED' AND dispatch_status IN ('NONE','ASSIGNED')",
        (staff_id, resource_id, utcnow(), request_id))
    if cur.rowcount != 1:
        raise StateConflict("Resources can only be assigned to an approved request that is not yet dispatched.")
    _event(con, request_id, "ASSIGNED", actor, {"staff_id": staff_id, "resource_id": resource_id})


def assign(request_id, actor, staff_id=None, resource_id=None):
    if not staff_id and not resource_id:
        raise ValueError("Choose a staff member or a mobility resource to assign.")
    with tx() as con:
        _assign(con, request_id, actor, staff_id, resource_id)
        req = con.execute("SELECT booking_ref FROM dispatch_requests WHERE id=?", (request_id,)).fetchone()
        if req and req["booking_ref"]:
            notify(con, req["booking_ref"], request_id, "ASSIGNED",
                   "Staff/equipment have been assigned to your approved request. Dispatch is not confirmed yet.")
    return get(request_id)


def advance_dispatch(request_id, actor, new_state):
    """Only real operational updates move the dispatch state, one step at a time."""
    if new_state not in DISPATCH_FLOW[2:]:
        raise ValueError(f"Unsupported dispatch state {new_state}")
    expected = DISPATCH_FLOW[DISPATCH_FLOW.index(new_state) - 1]
    with tx() as con:
        req = con.execute("SELECT * FROM dispatch_requests WHERE id=?", (request_id,)).fetchone()
        if not req or req["status"] != "APPROVED":
            raise StateConflict("Only approved requests can be dispatched.")
        if not (req["assigned_staff_id"] or req["assigned_resource_id"]):
            raise StateConflict("Assign staff or equipment before marking a dispatch.")
        cur = con.execute("UPDATE dispatch_requests SET dispatch_status=?, updated_at_utc=? WHERE id=? AND "
                          "dispatch_status=?", (new_state, utcnow(), request_id, expected))
        if cur.rowcount != 1:
            raise StateConflict(f"{request_id} is not in state {expected}.")
        _event(con, request_id, new_state, actor)
        if new_state == "COMPLETED":
            con.execute("UPDATE staff SET status='AVAILABLE' WHERE staff_id=?", (req["assigned_staff_id"],))
            con.execute("UPDATE mobility_resources SET status='AVAILABLE' WHERE resource_id=?",
                        (req["assigned_resource_id"],))
        if req["booking_ref"]:
            text = {"DISPATCHED": "The coordinator has confirmed that assistance has been dispatched to you.",
                    "EN_ROUTE": "Operational update: assistance staff are on their way to you.",
                    "COMPLETED": "Your assistance has been marked as completed. Have a good flight!"}[new_state]
            notify(con, req["booking_ref"], request_id, new_state, text)
    return get(request_id)


def escalate_if_overdue(request_id=None, after_s=ESCALATE_AFTER_S):
    """Stamp escalated_at on PENDING requests older than `after_s`. Never changes the decision."""
    rows = query("SELECT * FROM dispatch_requests WHERE status='PENDING' AND escalated_at IS NULL"
                 + (" AND id=?" if request_id else ""), (request_id,) if request_id else ())
    from db import seconds_since
    out = []
    for r in rows:
        if seconds_since(r["created_at_utc"]) >= after_s:
            with tx() as con:
                cur = con.execute("UPDATE dispatch_requests SET escalated_at=?, updated_at_utc=? WHERE id=? AND "
                                  "status='PENDING' AND escalated_at IS NULL", (utcnow(), utcnow(), r["id"]))
                if cur.rowcount:
                    _event(con, r["id"], "ESCALATED", "system", {"waited_s": seconds_since(r["created_at_utc"])})
                    if r["booking_ref"]:
                        notify(con, r["booking_ref"], r["id"], "ESCALATED",
                               "Your request is still waiting for a coordinator and has been escalated. "
                               "Nothing is confirmed yet.")
                    out.append(r["id"])
    return out


# ------------------------------------------------------------------ reads
def get(request_id):
    r = query_one("SELECT * FROM dispatch_requests WHERE id=?", (request_id,))
    if r:
        r["actions_list"] = json.loads(r["actions"] or "[]")
        r["context_dict"] = json.loads(r["context"] or "{}")
    return r


def latest_for_booking(booking_ref):
    r = query_one("SELECT id FROM dispatch_requests WHERE booking_ref=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                  (booking_ref,))
    return get(r["id"]) if r else None


def events(request_id):
    return query("SELECT * FROM request_events WHERE request_id=? ORDER BY id", (request_id,))


def notifications(booking_ref, limit=20):
    return query("SELECT * FROM notification_events WHERE booking_ref=? ORDER BY id DESC LIMIT ?", (booking_ref, limit))
