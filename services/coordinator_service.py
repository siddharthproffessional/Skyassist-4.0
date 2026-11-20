"""COORDINATOR SERVICE — the assistance lifecycle as airport staff see it.

Every public function takes a Principal and checks the COORDINATOR role in the backend, so hiding a
button is never the only protection. Decisions are atomic in SQLite and then wake the waiting agent.
"""
import json

import llm
import tools
from approval import get_engine
from db import query, seconds_since, tx, utcnow
from services import navigation_service, request_store
from services.auth_service import COORDINATOR, Principal, require_role
from services.passenger_service import demo_clock, verdict
from services.routing_engine import NoRouteError, profile_for

RISK_ORDER = {"AT_RISK": 0, "TIGHT": 1, "COMFORTABLE": 2}
RESOURCE_FOR = {"WHEELCHAIR_AT_DOOR": "WHEELCHAIR", "MOBILITY_CART": "CART"}
STAFF_FOR = {"WHEELCHAIR_AT_DOOR": "PRM agent", "MOBILITY_CART": "Cart driver", "STAFF_ESCORT": "Escort (minors)",
             "ESCORT_TO_TRANSFER_DESK": "PRM agent"}


def _enrich(r):
    ctx = r["context_dict"]
    slack_self = ctx.get("slack_self", ctx.get("slack", 0))
    r["risk"] = verdict(slack_self)
    r["risk_assisted"] = verdict(ctx.get("slack", 0))
    r["minutes_left"] = ctx.get("minutes_left")
    r["age_s"] = seconds_since(r["created_at_utc"])
    acts = r["actions_list"]
    r["tags"] = ([t for a, t in (("WHEELCHAIR_AT_DOOR", "Wheelchair"), ("STAFF_ESCORT", "Escort"),
                                 ("ESCORT_TO_TRANSFER_DESK", "Escort"), ("MOBILITY_CART", "Mobility cart"),
                                 ("GATE_HOLD_UP_TO_10_MIN", "Gate hold")) if a in acts])
    return r


def list_requests(principal: Principal, status_filter=None, tag_filter=None):
    require_role(principal, COORDINATOR)
    request_store.escalate_if_overdue()
    rows = [request_store.get(r["id"]) for r in query("SELECT id FROM dispatch_requests")]
    rows = [_enrich(r) for r in rows if r]
    if status_filter:
        def st(r):
            return "ESCALATED" if (r["status"] == "PENDING" and r["escalated_at"]) else r["status"]
        rows = [r for r in rows if st(r) in status_filter or (r["status"] in status_filter)]
    if tag_filter:
        rows = [r for r in rows if set(tag_filter) & set(r["tags"])]
    # AT RISK → TIGHT → COMFORTABLE; then least time remaining; ties broken by the worst unassisted shortfall
    rows.sort(key=lambda r: (r["status"] != "PENDING", RISK_ORDER.get(r["risk"], 3),
                             r["minutes_left"] if r["minutes_left"] is not None else 999,
                             r["context_dict"].get("slack_self", 0)))
    return rows


def kpis(principal: Principal):
    require_role(principal, COORDINATOR)
    reqs = query("SELECT status, dispatch_status, actions FROM dispatch_requests")
    connections = connection_board(principal)
    active = [c for c in connections if c["state"] == "OK"]
    return {
        "active_connections": len(active),
        "pending": sum(r["status"] == "PENDING" for r in reqs),
        "approved": sum(r["status"] == "APPROVED" for r in reqs),
        "declined": sum(r["status"] == "DECLINED" for r in reqs),
        "at_risk": sum(c.get("risk_self") == "AT_RISK" for c in active),
        "gate_holds": sum(r["status"] in ("PENDING", "APPROVED") and "GATE_HOLD" in r["actions"] for r in reqs),
        "active_assignments": sum(r["status"] == "APPROVED" and r["dispatch_status"] in
                                  ("ASSIGNED", "DISPATCHED", "EN_ROUTE") for r in reqs),
    }


def connection_board(principal: Principal):
    """Every booking's connection, computed live by the deterministic engine (no stored guesses)."""
    require_role(principal, COORDINATOR)
    out = []
    for p in query("SELECT * FROM passengers ORDER BY booking_ref"):
        needs = json.loads(p["needs"])
        row = {"booking_ref": p["booking_ref"], "passenger": p["lead_name"], "needs": needs,
               "inbound": p["inbound"], "outbound": p["outbound"], "state": "OK"}
        inb = tools.get_flight_and_gate_status(p["inbound"]) if p["inbound"] else {"found": False}
        outb = tools.get_flight_and_gate_status(p["outbound"]) if p["outbound"] else {"found": False}
        if not (inb.get("found") and outb.get("found")):
            row["state"] = "UNVERIFIED"
        elif outb["status"] == "CANCELLED":
            row["state"] = "CANCELLED"
        else:
            left = tools.minutes_until(outb["boarding_close"], demo_clock(p["booking_ref"]))
            try:
                plan = tools.decide_assistance(needs, inb["gate"], outb["gate"], left)
                row.update(arr_gate=inb["gate"], dep_gate=outb["gate"], minutes_left=left,
                           self_min=plan["self"]["total_min"], assisted_min=plan["plan"]["total_min"],
                           risk_self=verdict(plan["slack_self"]), decision=plan["decision"])
            except NoRouteError:
                row.update(state="NO_ROUTE", arr_gate=inb["gate"], dep_gate=outb["gate"], minutes_left=left)
        out.append(row)
    return out


def request_detail(principal: Principal, request_id):
    require_role(principal, COORDINATOR)
    r = request_store.get(request_id)
    if not r:
        return None
    r = _enrich(r)
    ctx = r["context_dict"]
    passenger = query("SELECT * FROM passengers WHERE booking_ref=?", (r["booking_ref"],))
    passenger = passenger[0] if passenger else None
    detail = {"request": r, "passenger": passenger, "events": request_store.events(request_id),
              "trace": query("SELECT actor, step, detail FROM trace WHERE conv_id=? ORDER BY id", (r["conv_id"],))}
    inb = tools.get_flight_and_gate_status(ctx["inbound"]) if ctx.get("inbound") else None
    outb = tools.get_flight_and_gate_status(ctx["outbound"]) if ctx.get("outbound") else None
    detail["inbound"], detail["outbound"] = inb, outb
    needs = ctx.get("needs", [])
    if inb and outb and inb.get("found") and outb.get("found"):
        mode = ctx.get("transfer_mode", "SELF")
        detail["route"] = navigation_service.preview_route(f"G_{inb['gate']}", outb["gate"],
                                                           profile_for(needs, mode if mode == "CART" else "SELF"))
        try:
            left = tools.minutes_until(outb["boarding_close"], ctx.get("now") or demo_clock(r["booking_ref"]))
            detail["policy_now"] = tools.decide_assistance(needs, inb["gate"], outb["gate"], left)
        except NoRouteError as e:
            detail["policy_now"] = {"error": str(e)}
        detail["gate_changed_since_request"] = outb["gate"] != ctx.get("dep_gate")
    detail["suggested"] = suggested_resources(r["actions_list"])
    facts = (f"{ctx.get('party')} needs {request_store.describe(r['actions_list'])}. Arriving {ctx.get('inbound')} at "
             f"gate {ctx.get('arr_gate')}, connecting to {ctx.get('outbound')} at gate {ctx.get('dep_gate')}, boarding "
             f"closes {ctx.get('boarding_close')} ({ctx.get('minutes_left')} min left). Transfer alone "
             f"{ctx.get('self_min', '?')} min, assisted {ctx.get('transfer_min')} min, spare {ctx.get('slack')} min.")
    detail["summary"], detail["summary_source"] = llm.summarize_situation(facts)
    return detail


def suggested_resources(actions):
    kinds = {RESOURCE_FOR[a] for a in actions if a in RESOURCE_FOR}
    roles = {STAFF_FOR[a] for a in actions if a in STAFF_FOR}
    res = query("SELECT * FROM mobility_resources WHERE status='AVAILABLE' ORDER BY resource_id")
    staff = query("SELECT * FROM staff WHERE status='AVAILABLE' ORDER BY staff_id")
    return {"resources": [x for x in res if x["kind"] in kinds] or res,
            "staff": [x for x in staff if x["role"] in roles] or staff, "all_resources": res, "all_staff": staff}


def decide(principal: Principal, request_id, approve: bool, note="", hold_minutes=None, staff_id=None,
           resource_id=None):
    """Atomic exactly-once decision, then wake the waiting agent. Raises StateConflict on a duplicate."""
    require_role(principal, COORDINATOR)
    r = request_store.decide(request_id, approve, principal.display_name, note, hold_minutes,
                             staff_id or None, resource_id or None)
    get_engine().notify_decided(request_id)
    return r


def assign(principal: Principal, request_id, staff_id=None, resource_id=None):
    require_role(principal, COORDINATOR)
    return request_store.assign(request_id, principal.display_name, staff_id or None, resource_id or None)


def advance(principal: Principal, request_id, new_state):
    require_role(principal, COORDINATOR)
    return request_store.advance_dispatch(request_id, principal.display_name, new_state)


def history(principal: Principal, limit=200):
    require_role(principal, COORDINATOR)
    return query("SELECT e.*, d.booking_ref FROM request_events e LEFT JOIN dispatch_requests d ON d.id=e.request_id "
                 "ORDER BY e.id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- synthetic-data simulator (ops page)
def _v3_bump_gate_versions(con, flight_no, old_gate, new_gate, actor):
    """SkyAssist 3.0 (additive): a gate change is a versioned state change, so approvals bound to these
    resources become stale. Skipped silently on a database without the v3 tables."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resource_versions'").fetchone():
        return
    from services.ops.foundation import audit, bump, outbox
    changed = [f"GATE:{new_gate}", f"GATE:{old_gate}", f"FLIGHT:{flight_no}"]
    for rid in changed:
        bump(con, rid, event=f"SIM_GATE_CHANGE {flight_no}->{new_gate}")
    audit(con, actor, "GATES", "GATE_ASSIGNED", "flight", flight_no, old={"gate": old_gate}, new={"gate": new_gate},
          reason="Coordinator gate change (v2 control)", result="COMMITTED")
    outbox(con, "state.changed", {"resources": changed, "reason": "gate change"})


def simulate_gate_change(principal: Principal, flight_no, new_gate):
    require_role(principal, COORDINATOR)
    new_gate = tools.normalize_gate(new_gate)
    if not new_gate or not query("SELECT 1 FROM gates WHERE gate=?", (new_gate,)):
        raise ValueError("Unknown gate.")
    with tx() as con:
        cur = con.execute("SELECT gate FROM flights WHERE flight_no=? AND direction='DEPARTURE'", (flight_no,)).fetchone()
        if not cur:
            raise ValueError("Unknown departure flight.")
        if cur["gate"] == new_gate:
            return
        con.execute("UPDATE flights SET previous_gate=gate, gate=?, status=CASE WHEN status IN ('ON_TIME','GATE_CHANGED')"
                    " THEN 'GATE_CHANGED' ELSE status END WHERE flight_no=?", (new_gate, flight_no))
        con.execute("INSERT INTO audit_log(actor,action,detail,created_at) VALUES(?,?,?,?)",
                    (principal.display_name, "SIM_GATE_CHANGE",
                     json.dumps({"flight": flight_no, "from": cur["gate"], "to": new_gate}), utcnow()))
        _v3_bump_gate_versions(con, flight_no, cur["gate"], new_gate, principal.display_name)
        for p in con.execute("SELECT booking_ref FROM passengers WHERE outbound=?", (flight_no,)).fetchall():
            request_store.notify(con, p["booking_ref"], None, "GATE_CHANGE",
                                 f"Gate change: {flight_no} now departs from Gate {new_gate} (was {cur['gate']}). "
                                 f"Your route has been updated.")


def set_edge_available(principal: Principal, edge_id, available: bool, reason=""):
    require_role(principal, COORDINATOR)
    with tx() as con:
        cur = con.execute("UPDATE terminal_edges SET available=?, closure_reason=? WHERE edge_id=?",
                          (int(available), None if available else (reason or "Closed"), edge_id))
        if cur.rowcount != 1:
            raise ValueError("Unknown corridor.")
        con.execute("INSERT INTO audit_log(actor,action,detail,created_at) VALUES(?,?,?,?)",
                    (principal.display_name, "SIM_EDGE_OPEN" if available else "SIM_EDGE_CLOSED",
                     json.dumps({"edge": edge_id, "reason": reason}), utcnow()))


def audit_log(principal: Principal, limit=100):
    require_role(principal, COORDINATOR)
    return query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
