"""ASSISTANCE SERVICE — creating requests and presenting their status truthfully to passengers."""
import json

import agent as agent_mod
from approval import get_engine
from services import request_store
from services.auth_service import Principal, require_booking_access
from services.request_store import ACTION_TEXT, describe

PASSENGER_SELECTABLE = ["WHEELCHAIR_AT_DOOR", "MOBILITY_CART", "STAFF_ESCORT"]


def chat_conv(booking_ref):
    return f"chat-{booking_ref}"


def request_from_policy(booking_ref, manifest, inbound, outbound, now, minutes_left, plan, source="POLICY"):
    """The deterministic policy says help is needed: create the durable request (idempotent) and
    attach the agent continuation that resumes after the human decision."""
    engine = get_engine()
    context = agent_mod.build_context(inbound, outbound, now, minutes_left, manifest["needs"], plan, manifest)
    req_id, created = engine.stage_ex(chat_conv(booking_ref), booking_ref, plan["actions"], plan["decision"],
                                      context, source=source)
    if created:
        agent_mod.log(chat_conv(booking_ref), "CODE",
                      f"Policy requested {describe(plan['actions'])} → {req_id} PENDING · agent paused (await)",
                      {"slack_self": plan["slack_self"], "slack_assisted": plan["slack"]})
        agent_mod.schedule_continuation(engine, req_id, chat_conv(booking_ref), plan["actions"], plan["decision"],
                                        inbound, outbound)
    return req_id, created


def passenger_request(principal: Principal, booking_ref, items, note, journey):
    """Passenger asks for help themselves (e.g. even when the policy did not require it)."""
    require_booking_access(principal, booking_ref)
    items = [i for i in items if i in PASSENGER_SELECTABLE]
    if not items:
        raise ValueError("Choose at least one type of assistance.")
    if journey.get("state") != "OK":
        raise ValueError("Assistance can be requested once your connection details are verified.")
    plan = dict(journey["plan"])
    plan["actions"] = items
    plan["decision"] = "PASSENGER_REQUEST"
    m = {"needs": journey["needs"], "lead_name": journey["passenger"], "party_size": journey["party_size"]}
    req_id, created = request_from_policy(booking_ref, m, journey["inbound"], journey["outbound"], journey["now"],
                                          journey["minutes_left"], plan, source="PASSENGER")
    if note and created:
        from db import tx, utcnow
        with tx() as con:
            con.execute("INSERT INTO request_events(request_id,event_type,actor,detail,created_at) VALUES(?,?,?,?,?)",
                        (req_id, "PASSENGER_NOTE", principal.username, json.dumps({"note": note}), utcnow()))
    return req_id, created


TRACK = ["REQUESTED", "PENDING COORDINATOR APPROVAL", "APPROVED", "DISPATCHED", "STAFF EN ROUTE", "COMPLETED"]


def passenger_view(booking_ref):
    """Translate the durable request into a passenger-facing state. Never upgrades a state on its own."""
    req = request_store.latest_for_booking(booking_ref)
    if not req:
        return {"state": "NO REQUEST REQUIRED", "request": None, "headline": "No assistance request",
                "detail": "You have not requested assistance.", "track_index": -1, "tone": "neutral"}
    items = describe(req["actions_list"])
    v = {"request": req, "items": items, "tone": "pending"}
    if req["status"] == "PENDING":
        v.update(state="ESCALATED" if req["escalated_at"] else "PENDING COORDINATOR APPROVAL", track_index=1,
                 headline="Waiting for airport coordinator approval",
                 detail=f"Your request for {items} has been submitted. It has not been confirmed yet. "
                        f"No staff dispatch has been confirmed." +
                        (" It is taking longer than expected and has been escalated." if req["escalated_at"] else ""))
    elif req["status"] == "DECLINED":
        v.update(state="DECLINED", track_index=1, tone="bad", headline="Assistance not approved",
                 detail=f"Your request was not approved by {req['resolved_by']}"
                        f"{' — ' + req['note'] if req['note'] else ''}. No staff are on the way. Please go to the "
                        f"nearest Transfer Desk or ask cabin crew at the aircraft door.")
    else:
        ds = req["dispatch_status"] or "NONE"
        hold = int(req.get("hold_minutes_approved") or 0)
        base = f"Approved by {req['resolved_by']}: {items}."
        if "GATE_HOLD_UP_TO_10_MIN" in req["actions_list"]:
            base += f" Gate hold approved for up to {hold} min." if hold else " The gate hold was not approved."
        if req["note"]:
            base += f" Note: {req['note'].rstrip('.')}."
        states = {
            "NONE": ("APPROVED", 2, "Request approved", " Staff have not been assigned or dispatched yet."),
            "ASSIGNED": ("APPROVED", 2, "Request approved — staff assigned",
                         " Staff/equipment are assigned. Dispatch is not confirmed yet."),
            "DISPATCHED": ("DISPATCHED", 3, "Assistance dispatched", " The coordinator has confirmed dispatch."),
            "EN_ROUTE": ("STAFF EN ROUTE", 4, "Staff on the way", " Operational update: staff are on their way."),
            "COMPLETED": ("COMPLETED", 5, "Assistance completed", ""),
        }
        state, idx, head, extra = states[ds]
        v.update(state=state, track_index=idx, tone="good", headline=head, detail=base + extra)
        v["assigned_staff"] = _name("staff", "staff_id", "name", req["assigned_staff_id"])
        v["assigned_resource"] = _name("mobility_resources", "resource_id", "label", req["assigned_resource_id"])
    return v


def _name(table, key, col, value):
    if not value:
        return None
    from db import query_one
    r = query_one(f"SELECT {col} FROM {table} WHERE {key}=?", (value,))
    return r[col] if r else value
