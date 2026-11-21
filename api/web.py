"""SkyAssist 4.0 — WEB API for the 3D digital twin frontend (router mounted at /web).

This is another interface to the existing system, not a replacement:
  * Human identities only. Sign-in uses the existing PBKDF2 demo accounts (services/auth_service.authenticate).
    The session cookie is HttpOnly + SameSite=Strict; every mutating call also needs the custom header
    `X-SkyAssist-Client: web` (blocks cross-site form posts / CSRF).
  * Every decision goes through the existing services, which re-check RBAC (require_controller etc.).
  * The n8n SERVICE adapter (api/app.py, /v1/*) is unchanged and still can never approve.
"""
import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from db import query, query_one
from services import coordinator_service
from services.agents import missions, runtime
from services.agents.registry import AGENTS, HUMAN_ONLY, tool_catalog
from services.auth_service import COORDINATOR, PASSENGER, AuthError, PermissionDenied, Principal, authenticate
from services.ops import crew, gate_approvals, journey, rebooking, simulator
from services.ops.foundation import OpsError, audit_now
from services.twin import state as twin

_ready = __import__("threading").Lock()


_db_ready = False


def ensure_database():
    """Serverless hosts may skip the ASGI lifespan and start with an empty /tmp: build the synthetic database
    (idempotent migrations + seed) before the first /web request that needs it."""
    import db
    global _db_ready
    if _db_ready and db.IS_PG:
        return
    if not db.database_exists():
        with _ready:
            if not db.database_exists():
                import build_db
                build_db.bootstrap()
    _db_ready = True


router = APIRouter(prefix="/web", dependencies=[Depends(ensure_database)])
SESSION_TTL_S = 8 * 3600
# Stateless signed session cookie (works on serverless hosts where requests may hit different instances).
# SKYASSIST_SESSION_SECRET must be set in shared deployments; without it a per-process random key is used, so a
# restart signs everyone out. The cookie carries only identity + role + expiry, signed with HMAC-SHA256; the role is
# re-checked by every service call anyway.
_SECRET = (os.getenv("SKYASSIST_SESSION_SECRET") or secrets.token_hex(32)).encode()
LIVE_EVENTS = os.getenv("SKYASSIST_SSE", "on").lower() != "off"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(p: Principal) -> str:
    body = _b64(json.dumps({"u": p.username, "r": p.role, "n": p.display_name, "b": p.booking_ref,
                            "exp": int(time.time()) + SESSION_TTL_S}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(tok: str) -> Optional[Principal]:
    try:
        body, sig = tok.split(".", 1)
        if not hmac.compare_digest(sig, _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())):
            return None
        d = json.loads(_unb64(body))
        if d["exp"] < time.time():
            return None
        return Principal(d["u"], d["r"], d["n"], d.get("b"))
    except Exception:
        return None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=100)
    portal: str = Field(pattern=r"^(COORDINATOR|PASSENGER)$")


class NoteIn(Strict):
    note: str = Field(default="", max_length=300)
    snapshot_hash: Optional[str] = Field(default=None, max_length=80)


class AlertIn(Strict):
    text: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="OCC", max_length=20)


class EdgeIn(Strict):
    available: bool
    reason: str = Field(default="", max_length=120)


class ScenarioIn(Strict):
    phase: Optional[str] = Field(default=None, pattern=r"^(invalid|valid)$")
    inject: Optional[str] = Field(default=None, pattern=r"^(after_seat|after_booking|after_bag|after_note)$")


class DelayIn(Strict):
    flight_no: str = Field(pattern=r"^[A-Z0-9]{2}-?\d{2,4}$")
    minutes: int = Field(ge=5, le=240)


class SimIn(Strict):
    provider: str = Field(pattern=r"^(gemini|groq)$")
    outage: Optional[bool] = None
    slow: Optional[bool] = None


class AssistIn(Strict):
    items: List[str] = Field(min_length=1, max_length=6)
    note: str = Field(default="", max_length=300)


# ------------------------------------------------------------------ session + guards
def _principal(request: Request) -> Optional[Principal]:
    return read_token(request.cookies.get("sa_session", ""))


def _csrf(request: Request, x_skyassist_client: str = Header(default="")):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and x_skyassist_client != "web":
        raise HTTPException(403, "Missing X-SkyAssist-Client header.")


def signed_in(request: Request, _=Depends(_csrf)) -> Principal:
    p = _principal(request)
    if p is None:
        raise HTTPException(401, "Sign in required.")
    return p


def controller(p: Principal = Depends(signed_in)) -> Principal:
    if p.role != COORDINATOR:
        raise HTTPException(403, "This requires an operations controller account.")
    return p


def passenger(p: Principal = Depends(signed_in)) -> Principal:
    if p.role != PASSENGER:
        raise HTTPException(403, "This is the passenger portal.")
    return p


def _ops(fn):
    try:
        return fn()
    except OpsError as e:
        raise HTTPException(422, {"code": e.code, "message": str(e)})
    except PermissionDenied as e:
        raise HTTPException(403, str(e))
    except runtime.ToolRefused as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(422, {"code": "INVALID", "message": str(e)})


# ------------------------------------------------------------------ auth
@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, _=Depends(_csrf)):
    try:
        p = authenticate(body.username, body.password, body.portal)
    except AuthError as e:
        raise HTTPException(401, str(e))
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie("sa_session", issue_token(p), httponly=True, samesite="strict", secure=https,
                        max_age=SESSION_TTL_S, path="/")
    return {"username": p.username, "role": p.role, "display_name": p.display_name, "booking_ref": p.booking_ref}


@router.post("/auth/logout")
def logout(request: Request, response: Response, _=Depends(_csrf)):
    response.delete_cookie("sa_session", path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    p = _principal(request)
    if not p:
        return {"signed_in": False}
    return {"signed_in": True, "username": p.username, "role": p.role, "display_name": p.display_name,
            "booking_ref": p.booking_ref}


# ------------------------------------------------------------------ twin
@router.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0", "label": twin.DATA_LABEL, "live_events": LIVE_EVENTS}


@router.get("/twin/layout")
def layout(p=Depends(signed_in)):
    return twin.layout()


@router.get("/twin/geometry")
def twin_geometry(p=Depends(signed_in)):
    from services.twin.geometry_sources import active_source
    return active_source().describe()


@router.get("/twin/state")
def twin_state(p=Depends(controller)):
    return twin.twin_state()


@router.get("/twin/version")
def twin_version(p=Depends(signed_in)):
    return {"version": twin.state_version()}


@router.get("/events")
async def events(request: Request):
    """Server-sent events: a 'state' event whenever the authoritative state version changes (audit, agent steps,
    corridor changes). The browser then refetches. No state is pushed through this channel itself."""
    if _principal(request) is None:
        raise HTTPException(401, "Sign in required.")
    if not LIVE_EVENTS:
        return Response(status_code=204)

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            v = await asyncio.to_thread(twin.state_version)
            if v != last:
                last = v
                yield f"event: state\ndata: {json.dumps({'version': v})}\n\n"
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/flights/{flight_no}")
def flight(flight_no: str, p=Depends(controller)):
    r = twin.flight_profile(flight_no.upper())
    if not r:
        raise HTTPException(404, "Flight not found in flight data.")
    return r


@router.get("/gates/{gate}")
def gate(gate: str, p=Depends(controller)):
    import tools
    g = tools.normalize_gate(gate)
    r = twin.gate_detail(g) if g else None
    if not r:
        raise HTTPException(404, "Unknown gate.")
    return r


@router.get("/routes/connections")
def connection_routes(flight: Optional[str] = None, p=Depends(controller)):
    return {"routes": twin.connection_routes(flight.upper() if flight else None),
            "note": "Planned transfer routes for recorded connections — not live passenger tracking."}


@router.get("/routes/baggage")
def baggage_routes(flight: Optional[str] = None, p=Depends(controller)):
    return {"legs": twin.baggage_paths(flight.upper() if flight else None)}


@router.get("/route")
def route(origin: str, dest: str, profile: str = "STANDARD", p=Depends(signed_in)):
    from services.routing_engine import PROFILES, get_engine
    if profile not in PROFILES:
        raise HTTPException(422, "Unknown profile.")
    return twin._route(get_engine(), origin, dest, profile)


@router.get("/connections")
def connections(p=Depends(controller)):
    return {"connections": coordinator_service.connection_board(p)}


@router.post("/corridors/{edge_id}")
def corridor(edge_id: str, body: EdgeIn, p=Depends(controller)):
    before = twin.connection_routes()
    used = [r for r in before if r.get("ok") and edge_id in r["edge_path"]]
    _ops(lambda: coordinator_service.set_edge_available(p, edge_id, body.available, body.reason))
    after = {(r["from"], r["to"], r["profile"]): r for r in twin.connection_routes()}
    changes = [{"before": r, "after": after.get((r["from"], r["to"], r["profile"]))} for r in used]
    return {"edge_id": edge_id, "available": body.available, "affected_routes": changes}


# ------------------------------------------------------------------ agents & missions
@router.get("/agents")
def agents(p=Depends(controller)):
    return {"agents": runtime.agent_statuses(), "tools": tool_catalog(), "human_only": HUMAN_ONLY}


@router.get("/missions")
def mission_list(limit: int = Query(20, ge=1, le=100), p=Depends(controller)):
    return {"missions": runtime.missions(limit)}


@router.get("/missions/{mission_id}")
def mission_get(mission_id: str, p=Depends(controller)):
    m = runtime.mission(mission_id)
    if not m:
        raise HTTPException(404, "Mission not found.")
    return m


@router.post("/agents/boundary-test")
def boundary(p=Depends(controller)):
    return missions.boundary_test(p)


@router.post("/alerts")
def alert(body: AlertIn, p=Depends(controller)):
    return _ops(lambda: missions.alert(p, body.text, body.source))


@router.get("/alerts/samples")
def alert_samples(p=Depends(controller)):
    return {"samples": journey.SAMPLES}


# ------------------------------------------------------------------ scenarios (all trigger real backend operations)
@router.get("/scenarios")
def scenarios(p=Depends(controller)):
    return {"scenarios": missions.scenario_status(), "metrics": twin.recovery_metrics()}


@router.post("/scenarios/reset")
def reset(p=Depends(controller)):
    _ops(lambda: simulator.reset(p))
    return {"ok": True, "label": "Synthetic operations dataset restored. Audit history and sign-offs are kept."}


@router.post("/scenarios/{code}/run")
def run_scenario(code: str, body: ScenarioIn, p=Depends(controller)):
    if code not in missions.SCENARIO_RUNNERS:
        raise HTTPException(404, "Unknown scenario.")
    kw = {}
    if code == "U-4.3" and body.phase:
        kw["phase"] = body.phase
    if code == "U-4.4" and body.inject:
        kw["inject"] = body.inject
    return _ops(lambda: missions.SCENARIO_RUNNERS[code](p, **kw))


@router.post("/scenarios/U-4.5/conflict")
def u45_conflict(p=Depends(controller)):
    return _ops(lambda: missions.u45_conflict(p))


@router.post("/scenarios/delay")
def delay(body: DelayIn, p=Depends(controller)):
    from services.ops import disruptions
    return _ops(lambda: disruptions.delay_flight(p, body.flight_no, body.minutes))


@router.post("/demo/investigate")
def demo_investigate(p=Depends(controller)):
    return _ops(lambda: missions.investigate(p))


@router.get("/recovery/metrics")
def recovery_metrics(p=Depends(controller)):
    return twin.recovery_metrics()


# ------------------------------------------------------------------ unified approval centre
def _gate_item(a):
    snap = json.loads(a["snapshot"])
    payload = json.loads(a["action_payload"])
    return {
        "kind": "gate", "id": a["approval_id"], "status": a["status"], "flight": a["flight_no"],
        "policy": "Gate move approval — expires after approvals.gate_move_ttl_min (30 min demo policy)",
        "title": f"Move {a['flight_no']} to Gate {payload['gate']}",
        "recommendation": f"Move {a['flight_no']} from {snap['flight_current_gate']} to {payload['gate']}.",
        "why": a.get("stale_reason") or ("Re-staged after a stale approval" if a.get("parent_id") else
                                         "Requested gate change (frees the current gate)."),
        "validations_passed": [f"Gate {payload['gate']} was free when staged",
                               f"Versions recorded: {snap['versions']}"],
        "validations_failed": [a["stale_reason"]] if a.get("stale_reason") else [],
        "state_change": f"flights.gate {a['flight_no']}: {snap['flight_current_gate']} → {payload['gate']}; "
                        f"resource versions bumped; passengers notified",
        "risks": "If another flight takes the gate before execution, execution is refused and a fresh proposal "
                 "is staged.",
        "if_declined": "Nothing changes. The flight stays at its current gate.",
        "expires_at": a["expires_at"], "state_version": snap["versions"], "snapshot_hash": a["snapshot_hash"],
        "can_execute": a["status"] == "APPROVED", "parent_id": a.get("parent_id"),
        "superseded_by": a.get("superseded_by"), "requested_at": a["requested_at"],
        "decided_by": a.get("decided_by")}


def _journey_item(a):
    pl = json.loads(a["payload"] or "{}")
    return {
        "kind": "journey", "id": a["approval_id"], "status": a["status"], "flight": a["flight_no"],
        "policy": "Round 3 paused risky action — 15-minute expiry, safe default = no change",
        "title": f"{a['action'].replace('_', ' ').title()} — {a['booking_ref']}",
        "recommendation": f"Rebook {a['booking_ref']} on {pl.get('target')}" +
                          (f"; bags travel separately on {pl.get('bag_flight')}" if pl.get("bag_flight") else ""),
        "why": a["risk_reason"],
        "validations_passed": ["Passenger connection feasible (deterministic transfer calculator)",
                               f"Viable bag flight found: {pl.get('bag_flight')}" if pl.get("bag_flight") else
                               "Plan computed by the baggage service"],
        "validations_failed": ["Bag connection below the 45-min minimum" if pl.get("plan") == "SEPARATE_FLIGHT"
                               else a["risk_reason"]],
        "state_change": "Seat + booking + bag assignment + delivery note committed in ONE transaction "
                        "(re-validated at execution)",
        "risks": "Bags will not arrive with the passenger.",
        "if_declined": "No rebooking is made; the booking stays on the cancelled flight for manual handling.",
        "expires_at": a["expires_at"], "state_version": None, "snapshot_hash": None, "can_execute": False,
        "requested_at": a["created_at"], "decided_by": a.get("decided_by")}


def _crew_item(c):
    v = json.loads(c["validation"] or "{}")
    return {
        "kind": "crew", "id": c["proposal_id"], "status": c["status"], "flight": c["flight_no"],
        "policy": "Crew assignment — legality re-validated at execution; no expiry configured",
        "title": f"Replace {c['replace_crew_id']} with {c['candidate_crew_id']} on {c['flight_no']}",
        "recommendation": f"Assign reserve {c['candidate_crew_id']} as {c['role'].replace('_', ' ').lower()}.",
        "why": f"{c['replace_crew_id']} does not have the {c['required_min']} min of duty the operation requires.",
        "validations_passed": [f"{ch['check']}: {ch.get('detail', '')}" for ch in v.get("checks", [])
                               if ch.get("result") is True][:8],
        "validations_failed": [f"{ch['check']}: {ch.get('detail', '')}" for ch in v.get("checks", [])
                               if ch.get("result") is False][:8],
        "state_change": f"flight_crew: {c['replace_crew_id']} REPLACED, {c['candidate_crew_id']} ASSIGNED; crew "
                        "hold cleared only if every member is LEGAL",
        "risks": "If the candidate is no longer legal at execution, the approval is refused.",
        "if_declined": "Departure stays blocked — current crew is not legally available.",
        "expires_at": None, "state_version": f"remaining {c['remaining_min']} min vs required {c['required_min']}",
        "snapshot_hash": None, "can_execute": False, "requested_at": c["created_at"],
        "decided_by": c.get("decided_by")}


def _batch_item(b, job):
    return {
        "kind": "batch", "id": b["batch_id"], "status": b["status"], "flight": job["target_flight"],
        "policy": "Escalated rebooking batch — controller decides whether to retry with fresh availability",
        "title": f"Batch {b['seq']} of {job['job_id']} escalated",
        "recommendation": "Retry the batch with fresh seat availability.",
        "why": b["last_error"] or "Retries exhausted.",
        "validations_passed": ["Earlier committed batches are preserved (independent transactions)"],
        "validations_failed": [b["last_error"] or "seat conflict"],
        "state_change": f"Up to {b['passenger_count']} seats reserved on {job['target_flight']} in one batch "
                        "transaction",
        "risks": "If the conflict persists the batch rolls back again — nothing else is affected.",
        "if_declined": f"{b['passenger_count']} passengers remain for manual rebooking.",
        "expires_at": None, "state_version": f"attempts {b['attempts']}", "snapshot_hash": None,
        "can_execute": False, "requested_at": job["created_at"], "decided_by": None}


def _assist_item(r):
    from services import request_store
    try:
        what = request_store.describe(json.loads(r.get("actions") or "[]"))
    except Exception:
        what = r.get("actions")
    return {
        "kind": "assistance", "id": r["id"], "status": r["status"], "flight": None,
        "policy": "Passenger assistance — escalates after 90 s pending (SkyAssist 2.0 policy); escalation never "
                  "approves",
        "title": f"Assistance for {r['booking_ref']}",
        "recommendation": f"Approve: {what}" if what else "Passenger assistance request",
        "why": f"Deterministic assistance policy decision {r.get('reason')} for this connection (SkyAssist 2.0)",
        "validations_passed": ["Transfer time and route computed by the deterministic routing engine"],
        "validations_failed": [],
        "state_change": "Request APPROVED/DECLINED; dispatch is a separate later step",
        "risks": "", "if_declined": "Passenger is told no staff are on the way and directed to the Transfer Desk.",
        "expires_at": None, "state_version": None, "snapshot_hash": None, "can_execute": False,
        "requested_at": r.get("created_at_utc"), "decided_by": r.get("resolved_by")}


@router.get("/approvals")
def approvals(p=Depends(controller)):
    journey.expire_stale()
    items = [_gate_item(a) for a in query("SELECT * FROM approval_requests ORDER BY requested_at DESC LIMIT 40")]
    items += [_journey_item(a) for a in query("SELECT * FROM journey_approvals ORDER BY created_at DESC LIMIT 40")]
    items += [_crew_item(c) for c in query("SELECT * FROM crew_assignment_proposals ORDER BY created_at DESC LIMIT 40")]
    for b in query("SELECT * FROM rebooking_batches WHERE status='ESCALATED'"):
        job = query_one("SELECT * FROM rebooking_jobs WHERE job_id=?", (b["job_id"],))
        items.append(_batch_item(b, job))
    items += [_assist_item(r) for r in query("SELECT * FROM dispatch_requests ORDER BY created_at DESC LIMIT 20")]
    pending = {"PENDING", "APPROVED", "PENDING_APPROVAL", "ESCALATED"}
    items.sort(key=lambda i: (i["status"] not in pending, str(i.get("requested_at") or "")), reverse=False)
    return {"items": items, "pending": sum(i["status"] in pending and not (i["kind"] == "gate" and
                                                                          i["status"] == "APPROVED") for i in items)}


@router.post("/approvals/{kind}/{item_id}/approve")
def approve(kind: str, item_id: str, body: NoteIn, p=Depends(controller)):
    note = body.note or "Approved in the SkyAssist 4.0 Approval Centre"
    if kind == "gate":
        a = gate_approvals.get(item_id)
        if not a:
            raise HTTPException(404, "Approval not found.")
        return _ops(lambda: _gate_item(gate_approvals.approve(p, item_id, body.snapshot_hash or "", note)))
    if kind == "journey":
        return _ops(lambda: journey.decide(p, item_id, True, note))
    if kind == "crew":
        return _ops(lambda: crew.decide_proposal(p, item_id, True, note))
    if kind == "batch":
        return _ops(lambda: rebooking.retry_escalated(p, item_id))
    if kind == "assistance":
        return _ops(lambda: coordinator_service.decide(p, item_id, True, note))
    raise HTTPException(404, "Unknown approval kind.")


@router.post("/approvals/{kind}/{item_id}/decline")
def decline(kind: str, item_id: str, body: NoteIn, p=Depends(controller)):
    note = body.note or "Declined in the SkyAssist 4.0 Approval Centre"
    if kind == "gate":
        return _ops(lambda: _gate_item(gate_approvals.reject(p, item_id, note)))
    if kind == "journey":
        return _ops(lambda: journey.decide(p, item_id, False, note))
    if kind == "crew":
        return _ops(lambda: crew.decide_proposal(p, item_id, False, note))
    if kind == "assistance":
        return _ops(lambda: coordinator_service.decide(p, item_id, False, note))
    raise HTTPException(422, "This item cannot be declined here.")


@router.post("/approvals/{kind}/{item_id}/reassess")
def reassess(kind: str, item_id: str, body: NoteIn, p=Depends(controller)):
    """Request reassessment: re-run the deterministic checks against the CURRENT state. For a gate move the old
    request is declined and a fresh proposal (new snapshot) is staged for a new decision."""
    if kind == "gate":
        a = gate_approvals.get(item_id)
        if not a or a["status"] != "PENDING":
            raise HTTPException(422, "Only a pending gate move can be reassessed.")

        def go():
            gate_approvals.reject(p, item_id, "Reassessment requested by controller")
            new = gate_approvals.stage_gate_move(p, a["flight_no"], a["payload_dict"]["gate"], parent_id=item_id,
                                                 note="Fresh proposal after reassessment request")
            return {"reassessed": True, "new_item": _gate_item(new)}
        return _ops(go)
    if kind == "journey":
        a = query_one("SELECT * FROM journey_approvals WHERE approval_id=?", (item_id,))
        if not a:
            raise HTTPException(404, "Approval not found.")
        pl = json.loads(a["payload"])
        from services.ops import baggage
        fresh = _ops(lambda: baggage.calculate_baggage_feasibility(pl["booking_ref"], pl["target"]))
        audit_now(p.display_name, "JOURNEY", "REASSESSMENT_REQUESTED", entity_type="journey_approval",
                  entity_id=item_id, new={"decision": fresh.get("decision")}, result="NO_CHANGE")
        return {"reassessed": True, "fresh_validation": fresh}
    if kind == "crew":
        c = query_one("SELECT * FROM crew_assignment_proposals WHERE proposal_id=?", (item_id,))
        if not c:
            raise HTTPException(404, "Proposal not found.")
        fresh = crew.validate_crew_legality(c["flight_no"], c["candidate_crew_id"], c["required_min"], as_reserve=True)
        audit_now(p.display_name, "CREW", "REASSESSMENT_REQUESTED", entity_type="crew_proposal", entity_id=item_id,
                  new={"verdict": fresh["verdict"]}, result="NO_CHANGE")
        return {"reassessed": True, "fresh_validation": fresh}
    raise HTTPException(422, "Reassessment is not available for this item.")


@router.post("/approvals/gate/{item_id}/execute")
def execute_gate(item_id: str, p=Depends(controller)):
    res = _ops(lambda: gate_approvals.execute(p, item_id))
    if res and res.get("new_approval_id"):
        res["new_item"] = _gate_item(query_one("SELECT * FROM approval_requests WHERE approval_id=?",
                                               (res["new_approval_id"],)))
    return res


# ------------------------------------------------------------------ audit
def _audit_rows(flight=None, passenger=None, agent=None, module=None, date=None, event_type=None, result=None,
                limit=300):
    where, args = [], []
    if flight:
        where.append("(entity_id=? OR old_state LIKE ? OR new_state LIKE ? OR reason LIKE ?)")
        args += [flight, f"%{flight}%", f"%{flight}%", f"%{flight}%"]
    if passenger:
        where.append("(entity_id=? OR old_state LIKE ? OR new_state LIKE ? OR reason LIKE ?)")
        args += [passenger, f"%{passenger}%", f"%{passenger}%", f"%{passenger}%"]
    if agent:
        mods = {"flight_intel": ["JOURNEY"], "passenger_recovery": ["REBOOKING"], "crew_compliance": ["CREW"],
                "maintenance": ["MAINTENANCE"], "baggage": ["BAGGAGE"], "gate_resource": ["GATES"],
                "communication": ["JOURNEY"], "safety_supervisor": ["AGENTS", "API"]}.get(agent, [])
        if mods:
            where.append(f"module IN ({','.join('?' * len(mods))})")
            args += mods
    if module:
        where.append("module=?")
        args.append(module)
    if date:
        where.append("occurred_at LIKE ?")
        args.append(f"{date}%")
    if event_type:
        where.append("event_type LIKE ?")
        args.append(f"%{event_type.upper()}%")
    if result:
        where.append("result=?")
        args.append(result.upper())
    sql = "SELECT * FROM audit_events" + (" WHERE " + " AND ".join(where) if where else "") + \
          " ORDER BY event_id DESC LIMIT ?"
    return query(sql, args + [limit])


AUDIT_FIELDS = ["event_id", "occurred_at", "actor", "module", "event_type", "entity_type", "entity_id", "txn_id",
                "result", "reason", "old_state", "new_state"]


@router.get("/audit")
def audit(flight: Optional[str] = None, passenger: Optional[str] = None, agent: Optional[str] = None,
          module: Optional[str] = None, date: Optional[str] = None, event_type: Optional[str] = None,
          result: Optional[str] = None, limit: int = Query(300, ge=1, le=2000), p=Depends(controller)):
    rows = _audit_rows(flight, passenger, agent, module, date, event_type, result, limit)
    modules = [r["module"] for r in query("SELECT DISTINCT module FROM audit_events WHERE module IS NOT NULL")]
    results = [r["result"] for r in query("SELECT DISTINCT result FROM audit_events WHERE result IS NOT NULL")]
    return {"events": rows, "modules": sorted(modules), "results": sorted(results),
            "total": query_one("SELECT COUNT(*) n FROM audit_events")["n"],
            "append_only": "audit_events cannot be updated or deleted (DB triggers trg_audit_no_update / _no_delete)"}


@router.get("/audit.csv")
def audit_csv(flight: Optional[str] = None, passenger: Optional[str] = None, agent: Optional[str] = None,
              module: Optional[str] = None, date: Optional[str] = None, event_type: Optional[str] = None,
              result: Optional[str] = None, p=Depends(controller)):
    rows = _audit_rows(flight, passenger, agent, module, date, event_type, result, 5000)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=AUDIT_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=skyassist_audit.csv"})


@router.get("/journey/{run_id}")
def journey_run(run_id: str, p=Depends(controller)):
    r = journey.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found.")
    return r


# ------------------------------------------------------------------ monitoring (Round 3 reliability)
@router.get("/monitoring")
def monitoring(p=Depends(controller)):
    from services.ai import gateway, pricing
    from services.ops import burst, outbox
    from services.ops.foundation import policy
    calls = query("SELECT provider, outcome, COUNT(*) n, AVG(latency_ms) avg_ms, SUM(tokens_in) tin, "
                  "SUM(tokens_out) tout FROM llm_calls GROUP BY provider, outcome")
    cost = sum(pricing.cost_usd(c["provider"], c["tin"] or 0, c["tout"] or 0) for c in calls)
    runs = query("SELECT status, COUNT(*) n, AVG(latency_ms) avg_ms, MAX(latency_ms) max_ms FROM journey_runs "
                 "GROUP BY status")
    dup = query_one("SELECT COUNT(*) n FROM audit_events WHERE event_type='JOURNEY_DUPLICATE'")["n"]
    blocked = query_one("SELECT COUNT(*) n FROM journey_runs WHERE safety_case='ATTACK_BLOCKED'")["n"]
    recent = query("SELECT run_id, created_at, source, status, alert_type, ai_provider, latency_ms, safety_case "
                   "FROM journey_runs ORDER BY created_at DESC LIMIT 25")
    lat = [r["latency_ms"] for r in query("SELECT latency_ms FROM journey_runs WHERE latency_ms IS NOT NULL "
                                          "ORDER BY latency_ms")]
    p50 = lat[len(lat) // 2] if lat else None
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
    retries = query_one("SELECT COUNT(*) n FROM llm_calls WHERE outcome='RETRY'")["n"]
    return {
        "chain": gateway.configured_chain(), "chain_order": ["gemini", "groq", "rules"],
        "health": twin.system_health(), "breakers": gateway.breaker_state(), "simulation": gateway.simulation_state(),
        "config": {"ai_call_timeout_s": gateway.TIMEOUT, "max_retries": gateway.MAX_RETRIES,
                   "retry_on": "timeout, connection error, HTTP 429, HTTP 5xx",
                   "circuit_breaker_after_failures": gateway.BREAK_AFTER, "circuit_open_for_s": gateway.BREAK_FOR,
                   "alert_timeout_s": int(policy("journey.run_timeout_s", "30")), "burst_workers": 4,
                   "journey_approval_ttl_min": int(policy("journey.approval_ttl_min", "15")),
                   "gate_move_ttl_min": int(policy("approvals.gate_move_ttl_min", "30")),
                   "assistance_escalate_after_s": 90},
        "llm_calls": calls, "estimated_cost_usd": round(cost, 6), "pricing_note": pricing.SOURCE_NOTE,
        "retries": retries, "journey": runs, "duplicates": dup, "blocked_attacks": blocked,
        "failed_workflows": query_one("SELECT COUNT(*) n FROM journey_runs WHERE status IN ('REJECTED','REFUSED')")["n"],
        "escalations": query_one("SELECT COUNT(*) n FROM rebooking_batches WHERE status='ESCALATED'")["n"],
        "latency_p50_ms": p50, "latency_p95_ms": p95, "alerts_processed": len(lat), "recent_runs": recent,
        "outbox": {"mode": outbox.mode(), "stats": outbox.stats()},
        "n8n_workflows": sorted(__import__("os").listdir(__import__("os").path.join(
            __import__("os").path.dirname(__import__("os").path.dirname(__file__)), "n8n", "workflows"))),
        "burst_last": getattr(burst, "LAST", None)}


@router.post("/monitoring/simulate")
def simulate(body: SimIn, p=Depends(controller)):
    from services.ai import gateway
    gateway.set_simulation(body.provider, outage=body.outage, slow=body.slow)
    audit_now(p.display_name, "MONITORING", "AI_SIMULATION_SET", entity_type="provider", entity_id=body.provider,
              new=gateway.simulation_state(), reason="SIMULATED provider condition (labelled)")
    return gateway.simulation_state()


@router.post("/monitoring/reset-breakers")
def reset_breakers(p=Depends(controller)):
    from services.ai import gateway
    gateway.reset_breakers()
    return gateway.breaker_state()


@router.post("/monitoring/burst")
def burst_run(p=Depends(controller)):
    from services.ops import burst
    return _ops(lambda: burst.run_burst(p, workers=4, fresh=True))


# ------------------------------------------------------------------ passenger portal
@router.get("/passenger/me")
def passenger_me(p=Depends(passenger)):
    from services import assistance_service, passenger_service, request_store
    from services.ops import baggage
    ref = p.booking_ref
    # same behaviour as the v2 passenger portal: the deterministic policy may raise an assistance REQUEST
    # (never an approval) when the passenger opens their journey
    j = _ops(lambda: passenger_service.get_journey(p, ref, auto_request=True))
    route = j.get("route_result")
    return {"booking_ref": ref, "passenger": p.display_name, "journey": _jsonable(j),
            "assistance": _jsonable(assistance_service.passenger_view(ref)),
            "baggage": baggage.passenger_baggage_view(ref),
            "notifications": request_store.notifications(ref, 20), "route": _jsonable(route),
            "label": twin.DATA_LABEL}


@router.post("/passenger/assistance")
def passenger_assist(body: AssistIn, p=Depends(passenger)):
    from services import assistance_service, passenger_service
    j = passenger_service.get_journey(p, p.booking_ref, auto_request=False)
    rid, created = _ops(lambda: assistance_service.passenger_request(p, p.booking_ref, body.items, body.note, j))
    return {"request_id": rid, "created": created}


@router.get("/passenger/route")
def passenger_route(dest: str, profile: str = "STANDARD", p=Depends(passenger)):
    from services.routing_engine import PROFILES, get_engine
    import tools
    if profile not in PROFILES:
        raise HTTPException(422, "Unknown profile.")
    m = tools.get_passenger_manifest(p.booking_ref)
    inb = tools.get_flight_and_gate_status(m["inbound"]) if m and m.get("inbound") else {}
    origin = inb.get("gate") or "HUB_B"
    return twin._route(get_engine(), origin, dest, profile)


def _jsonable(o):
    return json.loads(json.dumps(o, default=lambda x: x.__dict__ if hasattr(x, "__dict__") else str(x)))
