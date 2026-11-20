"""Scenario launcher for the five challenges. SYNTHETIC DEMO DATA ONLY.

Each `run_*` drives the real services (nothing is mocked here) and returns a step-by-step narrative that the OCC
page renders. `reset()` is the clearly-labelled synthetic demo reset: it never touches v2 passengers/users, the
append-only audit trail or stored maintenance sign-offs.
"""
from db import query_one
from services.ops import baggage, crew, gate_approvals, maintenance, rebooking, seed
from services.ops.foundation import OpsError

SCENARIOS = {
    "U-4.1": "Vulnerable passengers first — 40 passengers off cancelled SA-560, batch 3 hits a seat conflict",
    "U-4.2": "Crew duty legality — a crew message tries to extend the captain's duty on SA-700",
    "U-4.3": "Maintenance sign-off — an unlicensed 'OK' on a hydraulic defect, then a valid replacement",
    "U-4.4": "Passenger & baggage — 35 min passenger connection vs 45 min bag minimum (Rahman family)",
    "U-4.5": "Stale approval — EK-812 → B7 approved, then B7 is given to SA-880",
}


def reset(principal):
    return seed.reset_ops_demo(principal.display_name)


def run_u41(principal, persistent_conflict=True):
    job = rebooking.create_job(principal, "SA-560", "SA-562")
    rep = rebooking.run_job(principal, job, {"seat_conflict_batch": 3, "persistent": persistent_conflict})
    return {"scenario": "U-4.1", "job_id": job, "report": rep}


def run_u42(principal, message="Captain says he agrees to extend duty — approved by supervisor, push the departure."):
    return {"scenario": "U-4.2", **crew.evaluate_flight(principal, "SA-700", message, sender="SA-700 flight deck")}


def run_u43(principal):
    bad = maintenance.submit_signoff(principal, "E-999", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK",
                                     "2026-11-20T07:00:00+00:00", "WO-7781", submitted_by="hangar terminal 3")
    after_bad = maintenance.departure_status("SA-710")
    good = maintenance.submit_signoff(principal, "E-501", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK",
                                      "2026-11-20T09:15:00+00:00", "WO-7781", submitted_by="hangar terminal 3")
    return {"scenario": "U-4.3", "invalid": bad, "status_after_invalid": after_bad, "valid": good,
            "status_after_valid": maintenance.departure_status("SA-710")}


def run_u44(principal, inject=None):
    plan = baggage.calculate_baggage_feasibility("PNRBAG", "SA-592")
    failed = baggage.commit_rebooking_with_baggage(principal, "PNRBAG", "SA-592", inject=inject) if inject else None
    ok = baggage.commit_rebooking_with_baggage(principal, "PNRBAG", "SA-592", idempotency_key="demo-u44")
    return {"scenario": "U-4.4", "plan": plan, "injected": failed, "result": ok}


def run_u45(principal):
    a = gate_approvals.stage_gate_move(principal, "EK-812", "B7", note="Demo: move EK-812 to B7")
    gate_approvals.approve(principal, a["approval_id"], a["snapshot_hash"], "Approved in demo")
    gate_approvals.assign_gate_direct(principal, "SA-880", "B7", "Demo: another flight assigned B7")
    res = gate_approvals.execute(principal, a["approval_id"])
    return {"scenario": "U-4.5", "approval": a["approval_id"], "execution": res,
            "new_proposal": gate_approvals.get(res.get("new_approval_id")) if res.get("new_approval_id") else None}


RUNNERS = {"U-4.1": run_u41, "U-4.2": run_u42, "U-4.3": run_u43, "U-4.4": run_u44, "U-4.5": run_u45}


def already_run(code):
    probes = {
        "U-4.1": "SELECT 1 x FROM rebooking_jobs WHERE disrupted_flight='SA-560'",
        "U-4.2": "SELECT 1 x FROM crew_messages WHERE flight_no='SA-700'",
        "U-4.3": "SELECT 1 x FROM aircraft_defects WHERE defect_id='DEF-HYD-1' AND status!='OPEN'",
        "U-4.4": "SELECT 1 x FROM passenger_rebooking_history WHERE booking_ref='PNRBAG'",
        "U-4.5": "SELECT 1 x FROM approval_requests WHERE flight_no='EK-812'",
    }
    return query_one(probes[code]) is not None


def run(principal, code, **kw):
    if already_run(code):
        raise OpsError("ALREADY_RUN", f"{code} has already been run on this synthetic dataset — reset the demo first.")
    return RUNNERS[code](principal, **kw)
