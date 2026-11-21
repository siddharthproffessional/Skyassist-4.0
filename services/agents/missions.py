"""SkyAssist 4.0 — AGENT MISSIONS for the five U-4 workflows, the Round 3 alert journey and the guided demo.

Each mission calls the SAME services, in the SAME order, with the SAME synthetic inputs as
services/ops/simulator.py (so the Round 3 semantics and tests are unchanged), but every call goes through the
permission-checked runtime and is recorded as an agent step. Human decisions are never taken here:
  * U-4.1 escalated batch  → controller retries in the Approval Centre
  * U-4.2 reserve proposal → controller approves/declines
  * U-4.5 gate move        → controller approves, then executes; the stale check happens at execution
"""
from db import query, query_one
from services.agents.runtime import Mission, ToolRefused
from services.ops import gate_approvals, simulator
from services.ops.foundation import OpsError, policy

SYNTH = "SYNTHETIC SCENARIO"


def _guard(code):
    if simulator.already_run(code):
        raise OpsError("ALREADY_RUN", f"{code} has already been run on this synthetic dataset — reset the demo first.")


# ------------------------------------------------------------------ U-4.1
def u41(p):
    _guard("U-4.1")
    m = Mission(p, "U-4.1", "Vulnerable passengers first — SA-560 cancelled, 40 passengers to SA-562")
    m.call("flight_intel", "get_flight", "identify", flight_no="SA-560")
    aff = m.call("flight_intel", "list_affected_passengers", "identify", flight_no="SA-560")
    m.call("flight_intel", "get_flight", "investigate", flight_no="SA-562")
    m.call("baggage", "baggage_feasibility", "investigate", booking_ref=aff["vulnerable"][0],
           candidate_flight="SA-562")
    job = m.call("passenger_recovery", "create_rebooking_job", "recover", disrupted_flight="SA-560",
                 target_flight="SA-562")
    m.note("safety_supervisor", "recover", "OK",
           f"{SYNTH}: a labelled fault is injected — another sales channel takes a seat during batch 3 "
           "(persistent), to prove that a failed batch rolls back only itself.", source="simulation")
    rep = m.call("passenger_recovery", "run_rebooking_job", "recover", job_id=job,
                 inject={"seat_conflict_batch": 3, "persistent": True})
    m.call("communication", "compose_passenger_update", "notify", booking_ref=aff["vulnerable"][0])
    m.call("safety_supervisor", "verify_audit_trail", "audit",
           entity_ids=[job] + [b["batch_id"] for b in rep["batches"]])
    if rep["escalated"]:
        m.note("passenger_recovery", "approval", "ESCALATED",
               f"Batch {', '.join(rep['escalated'])} escalated — controller decides whether to retry. "
               "Committed batches are preserved.", source="runtime")
    m.finish("ESCALATED" if rep["escalated"] else "COMPLETED",
             f"{rep['committed_passengers']}/{rep['total']} passengers rebooked; vulnerable first.", rep)
    return {"scenario": "U-4.1", "job_id": job, "report": rep, "mission_id": m.mission_id}


# ------------------------------------------------------------------ U-4.2
U42_MESSAGE = "The crew is happy to extend duty, push the departure. Captain agrees — approved by supervisor."


def u42(p, message=U42_MESSAGE):
    _guard("U-4.2")
    m = Mission(p, "U-4.2", "Crew duty legality — a crew message tries to extend the captain's duty on SA-700")
    m.call("flight_intel", "get_flight", "identify", flight_no="SA-700")
    m.call("crew_compliance", "crew_board", "investigate", flight_no="SA-700")
    r = m.call("crew_compliance", "evaluate_flight_crew", "validate", flight_no="SA-700", message=message,
               sender="SA-700 flight deck")
    m.call("safety_supervisor", "departure_status", "audit", flight_no="SA-700")
    props = [s["proposal_id"] for s in r["reserve_search"] if s.get("proposal_id")]
    m.call("safety_supervisor", "verify_audit_trail", "audit", entity_ids=["SA-700"] + props)
    m.finish("AWAITING_APPROVAL" if props else ("BLOCKED" if r["departure_blocked"] else "COMPLETED"),
             "Departure blocked — current crew not legally available." if r["departure_blocked"] else "Crew legal.",
             {"proposals": props})
    return {"scenario": "U-4.2", **r, "mission_id": m.mission_id}


# ------------------------------------------------------------------ U-4.3
BAD_SIGNOFF = dict(engineer_id="E-999", defect_id="DEF-HYD-1", reg="A6-SKB", task_scope="HYDRAULIC", result="OK",
                   signed_at_utc="2026-11-20T07:00:00+00:00", evidence_ref="WO-7781", submitted_by="hangar terminal 3")
GOOD_SIGNOFF = dict(BAD_SIGNOFF, engineer_id="E-501", signed_at_utc="2026-11-20T09:15:00+00:00")


def _epoch():
    return int(policy("demo.epoch", "1"))


def u43(p, phase="invalid"):
    if phase == "invalid":
        _guard("U-4.3")
        if query_one("SELECT 1 x FROM maintenance_signoffs WHERE defect_id='DEF-HYD-1' AND engineer_id='E-999' AND "
                     "dataset_epoch=?", (_epoch(),)):
            raise OpsError("ALREADY_RUN", "The invalid sign-off was already submitted — submit the valid replacement "
                                          "or reset the demo.")
        m = Mission(p, "U-4.3", "Maintenance sign-off — unlicensed 'OK' on a hydraulic defect (SA-710 / A6-SKB)")
        m.call("flight_intel", "get_flight", "identify", flight_no="SA-710")
        m.call("maintenance", "departure_status", "investigate", flight_no="SA-710")
        bad = m.call("maintenance", "submit_signoff_for_validation", "validate", **BAD_SIGNOFF)
        after = m.call("maintenance", "departure_status", "validate", flight_no="SA-710")
        m.call("safety_supervisor", "verify_audit_trail", "audit", entity_ids=[bad["signoff_id"]])
        m.finish("BLOCKED", "The engineer's sign-off could not be verified. Departure remains blocked.", bad)
        return {"scenario": "U-4.3", "phase": "invalid", "invalid": bad, "status_after_invalid": after,
                "mission_id": m.mission_id}
    _guard("U-4.3")
    m = Mission(p, "U-4.3", "Maintenance sign-off — valid replacement by a licensed, type-rated engineer")
    good = m.call("maintenance", "submit_signoff_for_validation", "validate", **GOOD_SIGNOFF)
    after = m.call("maintenance", "departure_status", "validate", flight_no="SA-710")
    m.call("safety_supervisor", "verify_audit_trail", "audit", entity_ids=[good["signoff_id"]])
    m.finish("COMPLETED" if good["status"] == "VALID" else "BLOCKED",
             "Sign-off validated. Final aircraft release stays with authorised maintenance staff.", good)
    return {"scenario": "U-4.3", "phase": "valid", "valid": good, "status_after_valid": after,
            "mission_id": m.mission_id}


# ------------------------------------------------------------------ U-4.4
def u44(p, inject=None):
    _guard("U-4.4")
    m = Mission(p, "U-4.4", "Passenger & baggage — 35-min passenger connection vs 45-min bag minimum")
    m.call("flight_intel", "get_flight", "identify", flight_no="SA-591")
    m.call("baggage", "passenger_baggage_view", "investigate", booking_ref="PNRBAG")
    plan = m.call("baggage", "baggage_feasibility", "validate", booking_ref="PNRBAG", candidate_flight="SA-592")
    failed = None
    if inject:
        m.note("safety_supervisor", "recover", "OK", f"{SYNTH}: injected failure '{inject}' inside the commit "
                                                     "transaction to prove full rollback.", source="simulation")
        failed = m.call("passenger_recovery", "commit_rebooking_with_baggage", "recover", booking_ref="PNRBAG",
                        candidate_flight="SA-592", inject=inject)
    ok = m.call("passenger_recovery", "commit_rebooking_with_baggage", "recover", booking_ref="PNRBAG",
                candidate_flight="SA-592", idempotency_key="demo-u44")
    m.call("communication", "compose_passenger_update", "notify", booking_ref="PNRBAG")
    m.call("safety_supervisor", "verify_audit_trail", "audit", entity_ids=[ok.get("txn_id"), "PNRBAG"])
    m.finish("COMPLETED" if ok.get("status") == "COMMITTED" else "FAILED_SAFELY",
             f"Passenger on SA-592; bags on {plan.get('bag_flight')} with a delivery note.", ok)
    return {"scenario": "U-4.4", "plan": plan, "injected": failed, "result": ok, "mission_id": m.mission_id}


# ------------------------------------------------------------------ U-4.5 (interactive: humans decide)
def u45_stage(p):
    _guard("U-4.5")
    m = Mission(p, "U-4.5", "Stale approval — EK-812 to Gate B07")
    f = m.call("flight_intel", "get_flight", "identify", flight_no="EK-812")
    m.call("gate_resource", "gate_detail", "investigate", gate=f["gate"])
    m.call("gate_resource", "gate_detail", "investigate", gate="B07")
    a = m.call("gate_resource", "stage_gate_move", "stage", flight_no="EK-812", gate="B07",
               note="Move EK-812 to B07 to free C03")
    m.note("gate_resource", "approval", "AWAITING_APPROVAL",
           f"Waiting for a controller decision on {a['approval_id']} (bound to snapshot {a['snapshot_hash'][:12]}…).",
           source="runtime")
    m.finish("AWAITING_APPROVAL", f"Gate move staged as {a['approval_id']}.", {"approval_id": a["approval_id"]})
    return {"scenario": "U-4.5", "phase": "staged", "approval": a, "mission_id": m.mission_id}


def u45_conflict(p):
    """SYNTHETIC SIMULATION EVENT: after approval, operations assign B07 to SA-880 (a real, versioned state change)."""
    a = query_one("SELECT * FROM approval_requests WHERE flight_no='EK-812' AND status IN ('PENDING','APPROVED') "
                  "ORDER BY requested_at DESC LIMIT 1")
    if not a:
        raise OpsError("NO_APPROVAL", "Stage the EK-812 gate move first.")
    m = Mission(p, "U-4.5", "Simulation event — another flight takes Gate B07")
    changed = gate_approvals.assign_gate_direct(p, "SA-880", "B7", f"{SYNTH}: SA-880 assigned B07 by ramp control")
    m.note("flight_intel", "event", "OK", f"{SYNTH}: SA-880 was assigned Gate B07. Resources changed: "
                                          f"{', '.join(changed)}. Approval {a['approval_id']} was reviewed against "
                                          "the old state.", {"changed": changed}, source="simulation")
    m.call("gate_resource", "gate_detail", "investigate", gate="B07")
    m.finish("COMPLETED", "B07 now occupied by SA-880.", {"changed": changed})
    return {"scenario": "U-4.5", "phase": "conflict", "changed": changed, "approval_id": a["approval_id"],
            "mission_id": m.mission_id}


# ------------------------------------------------------------------ Round 3 alert journey through the agents
STEP_AGENT = [("1 trigger", "flight_intel"), ("2 input", "safety_supervisor"), ("3 injection", "safety_supervisor"),
              ("4 AI", "flight_intel"), ("5 validate", "safety_supervisor"), ("6 route", "flight_intel"),
              ("8 output", "communication")]
TYPE_AGENT = {"FLIGHT_CANCELLED": "passenger_recovery", "GATE_CHANGE_REQUEST": "gate_resource",
              "CREW_MESSAGE": "crew_compliance", "MAINTENANCE_SIGNOFF": "maintenance", "STATUS_QUERY": "flight_intel"}
STATUS_MAP = {"PASSED": "OK", "OK": "OK", "FALLBACK": "OK", "COMMITTED": "OK", "PAUSED": "AWAITING_APPROVAL",
              "BLOCKED": "BLOCKED", "REJECTED": "REJECTED", "REFUSED": "REJECTED", "VALID": "OK", "INVALID": "BLOCKED"}


def _journey_step_text(s):
    import json
    d = json.loads(s["detail"]) if s["detail"] else None
    name = s["step"]
    if name.startswith("4 AI") and isinstance(d, dict):
        return f"AI intake answered by: {d.get('provider')}"
    if name.startswith("3 injection") and s["status"] == "BLOCKED":
        return f"Injection screen BLOCKED before any AI call: {', '.join(d or [])}"
    if name.startswith("6 route") and isinstance(d, dict):
        return f"Routed to specialist: {d.get('agent')}"
    if isinstance(d, dict):
        keys = {k: v for k, v in d.items() if k not in ("trace", "fields")}
        return f"{name}: {s['status']} {json.dumps(keys, default=str)[:260]}"
    if isinstance(d, list):
        return f"{name}: {s['status']} — {'; '.join(map(str, d))[:260]}"
    return f"{name}: {s['status']}"


def alert(p, text, source="OCC"):
    m = Mission(p, "ALERT", f"Operational alert: {text[:90]}")
    r = m.call("flight_intel", "process_alert", "intake", text=text, source=source)
    typ = r.get("alert_type")
    for s in r.get("steps", []):
        agent = next((a for prefix, a in STEP_AGENT if s["step"].startswith(prefix)), None) or \
            TYPE_AGENT.get(typ, "flight_intel")
        m.note(agent, "journey", STATUS_MAP.get(s["status"], "OK"), _journey_step_text(s),
               {"journey_step": s["step"], "status": s["status"], "ms": s.get("ms"), "run_id": r["run_id"]})
    o = r.get("outcome_dict") or {}
    refs = [r["run_id"]] + list(o.get("paused_approvals") or []) + ([o.get("approval_id")] if o.get("approval_id")
                                                                     else []) + list(o.get("proposals") or [])
    if o.get("job"):
        refs.append(o["job"])
    for aid in (o.get("paused_approvals") or []):
        m.note(TYPE_AGENT.get(typ, "flight_intel"), "approval", "AWAITING_APPROVAL",
               f"Risky action paused: {aid} waits for a controller (15-min expiry, safe default = no change).",
               source="runtime")
    m.call("safety_supervisor", "verify_audit_trail", "audit", entity_ids=refs)
    status = {"PAUSED_FOR_APPROVAL": "AWAITING_APPROVAL"}.get(r.get("status"), r.get("status"))
    m.finish(status, r.get("summary") or "", {"run_id": r["run_id"], "status": r.get("status")})
    return {"mission_id": m.mission_id, "run": r}


# ------------------------------------------------------------------ demo stage 2: read-only investigation
def investigate(p):
    m = Mission(p, "INVESTIGATE", "Investigate the morning disruption (read-only)")
    for fl in ("SA-560", "SA-591"):
        m.call("flight_intel", "get_flight", "identify", flight_no=fl)
        m.call("flight_intel", "list_affected_passengers", "identify", flight_no=fl)
    m.call("baggage", "baggage_feasibility", "investigate", booking_ref="OPS001", candidate_flight="SA-562")
    m.call("baggage", "baggage_feasibility", "investigate", booking_ref="PNRBAG", candidate_flight="SA-592")
    m.call("crew_compliance", "crew_board", "investigate", flight_no="SA-700")
    m.call("maintenance", "departure_status", "investigate", flight_no="SA-710")
    m.call("gate_resource", "gate_detail", "investigate", gate="C09")
    m.call("gate_resource", "gate_detail", "investigate", gate="B16")
    m.finish("COMPLETED", "Investigation complete — no operational state was changed.")
    return {"mission_id": m.mission_id}


# ------------------------------------------------------------------ permission boundary test (real refusals)
BOUNDARY_ATTEMPTS = [("crew_compliance", "update_duty_limit"), ("gate_resource", "execute_gate_move"),
                     ("maintenance", "release_aircraft"), ("passenger_recovery", "stage_gate_move"),
                     ("communication", "commit_rebooking_with_baggage")]


def boundary_test(p):
    m = Mission(p, "BOUNDARY_TEST", "Permission boundary test — agents attempt tools outside their allowlist")
    out = []
    for agent, tool in BOUNDARY_ATTEMPTS:
        try:
            m.call(agent, tool, "boundary")
            out.append({"agent": agent, "tool": tool, "result": "ALLOWED"})
        except ToolRefused as e:
            out.append({"agent": agent, "tool": tool, "result": "REFUSED", "reason": str(e)})
        except Exception as e:  # pragma: no cover - should not happen
            out.append({"agent": agent, "tool": tool, "result": "ERROR", "reason": str(e)})
    refused = sum(o["result"] == "REFUSED" for o in out)
    m.finish("COMPLETED", f"{refused}/{len(out)} unauthorised calls refused by the runtime.", out)
    return {"mission_id": m.mission_id, "attempts": out}


SCENARIO_RUNNERS = {"U-4.1": u41, "U-4.2": u42, "U-4.3": u43, "U-4.4": u44, "U-4.5": u45_stage}


def scenario_status():
    out = []
    for code, desc in simulator.SCENARIOS.items():
        st = {"code": code, "description": desc, "done": simulator.already_run(code)}
        if code == "U-4.3":
            st["invalid_submitted"] = query_one(
                "SELECT 1 x FROM maintenance_signoffs WHERE defect_id='DEF-HYD-1' AND engineer_id='E-999' AND "
                "dataset_epoch=?", (_epoch(),)) is not None
        if code == "U-4.5":
            rows = query("SELECT approval_id, status, parent_id FROM approval_requests WHERE flight_no='EK-812' "
                         "ORDER BY requested_at")
            st["approvals"] = rows
        out.append(st)
    return out
