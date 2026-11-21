"""SkyAssist 4.0 — AGENT REGISTRY AND TOOLBOX.

Every agent is a named operational role with
  * a responsibility statement,
  * an explicit allowlist of tools (nothing else can be called — the runtime refuses and audits),
  * a list of things it can never do (no tool exists for them anywhere in the toolbox).

Every tool is a thin wrapper over an EXISTING deterministic SkyAssist service. Tools never write to tables
directly: writes happen only inside the services, which keep their own RBAC, validation, compare-and-set,
transactions and audit. There is deliberately NO tool that approves, executes an approved action, changes a
duty limit, releases an aircraft or overrides seat inventory: those are human decisions taken through the
controller API (require_controller) or are outside SkyAssist entirely.

Tool kinds
  READ      read-only lookup
  VALIDATE  deterministic Python validation (may record a validation result / hold, never a release)
  STAGE     creates a proposal that a human controller must decide
  COMMIT    a deterministic service commit that the existing policy allows without a human (e.g. U-4.1 safe
            rebooking batches, U-4.4 atomic seat+bag commit) — the service re-validates inside its transaction
  NOTIFY    passenger/controller wording (template-based, fact-guarded)
"""
import json

import tools as v2tools
from db import query, query_one
from services.ops import baggage, crew, gate_approvals, journey, maintenance, rebooking


# ------------------------------------------------------------------ helpers used by tools
def _flight(no):
    f = v2tools.get_flight_and_gate_status(no)
    if not f.get("found"):
        return {"found": False, "flight_no": no}
    return f


def _affected(flight_no):
    rows = query("SELECT booking_ref, lead_name, party_size, needs FROM passengers WHERE outbound=? "
                 "ORDER BY booking_ref", (flight_no,))
    for r in rows:
        r["needs"] = json.loads(r["needs"] or "[]")
    vuln = set(json.loads(query_one("SELECT value FROM ops_policies WHERE policy_key='rebooking.vulnerable_needs'")
                          ["value"])) if query_one("SELECT 1 x FROM ops_policies WHERE "
                                                   "policy_key='rebooking.vulnerable_needs'") else {"WCHR", "UMNR",
                                                                                                    "ELDERLY"}
    return {"flight_no": flight_no, "passengers": rows, "count": len(rows),
            "vulnerable": [r["booking_ref"] for r in rows if set(r["needs"]) & vuln],
            "vulnerable_rule": "recorded booking needs only (WCHR, UMNR, ELDERLY) — never inferred"}


def _compose_update(booking_ref):
    """Template wording from committed facts only (no LLM on this path, so nothing can be invented)."""
    hist = query_one("SELECT * FROM passenger_rebooking_history WHERE booking_ref=? ORDER BY id DESC LIMIT 1",
                     (booking_ref,))
    bags = baggage.passenger_baggage_view(booking_ref)
    if not hist:
        return {"booking_ref": booking_ref, "message": None, "reason": "No committed rebooking — nothing to tell yet."}
    msg = f"You have been rebooked from {hist['from_flight']} to {hist['to_flight']}"
    seat = hist.get("seat_no") or hist.get("seat")
    msg += f", seat {seat}." if seat else "."
    if bags and bags.get("separate"):
        fl = {a["flight_no"] for a in bags["assignments"]}
        msg += f" Your bags travel separately on {', '.join(sorted(fl))}; a delivery note has been issued."
    return {"booking_ref": booking_ref, "message": msg, "source": "template over committed records"}


def _verify_audit(entity_ids):
    ids = [e for e in entity_ids if e]
    if not ids:
        return {"checked": 0, "events": 0, "missing": []}
    q = ",".join("?" * len(ids))
    have = {r["entity_id"] for r in query(f"SELECT DISTINCT entity_id FROM audit_events WHERE entity_id IN ({q})", ids)}
    n = query_one(f"SELECT COUNT(*) n FROM audit_events WHERE entity_id IN ({q})", ids)["n"]
    return {"checked": len(ids), "events": n, "missing": [e for e in ids if e not in have]}


def _gate_detail(gate):
    g = v2tools.normalize_gate(gate)
    occ = query("SELECT flight_no, status, direction FROM flights WHERE gate=? AND status!='CANCELLED'", (g,))
    v = query_one("SELECT version FROM resource_versions WHERE resource_id=?", (f"GATE:{g}",))
    return {"gate": g, "occupants": occ, "version": v["version"] if v else 1}


# ------------------------------------------------------------------ toolbox: name -> (callable(principal, **kw), kind, description)
TOOLS = {
    # READ
    "get_flight": (lambda p, flight_no: _flight(flight_no), "READ", "Flight status, gate and times from flight data"),
    "list_affected_passengers": (lambda p, flight_no: _affected(flight_no), "READ",
                                 "Passengers booked on a flight, vulnerable ones identified from recorded needs"),
    "departure_status": (lambda p, flight_no: maintenance.departure_status(flight_no), "READ",
                         "Aggregated departure holds (crew, maintenance)"),
    "crew_board": (lambda p, flight_no: crew.crew_board(flight_no), "READ", "Assigned crew and duty records"),
    "gate_detail": (lambda p, gate: _gate_detail(gate), "READ", "Gate occupants and resource version"),
    "rebooking_report": (lambda p, job_id: rebooking.report(job_id), "READ", "Batch-by-batch rebooking report"),
    "passenger_baggage_view": (lambda p, booking_ref: baggage.passenger_baggage_view(booking_ref), "READ",
                               "Bags, active flight assignments, delivery note"),
    # VALIDATE (deterministic Python)
    "baggage_feasibility": (lambda p, booking_ref, candidate_flight:
                            baggage.calculate_baggage_feasibility(booking_ref, candidate_flight), "VALIDATE",
                            "Passenger + bag connection check against the 45-min minimum; finds a later bag flight"),
    "validate_crew_legality": (lambda p, flight_no, crew_id: crew.validate_crew_legality(flight_no, crew_id),
                               "VALIDATE", "Duty legality from immutable rule profile (UNKNOWN fails closed)"),
    "evaluate_flight_crew": (lambda p, flight_no, message=None, sender="crew channel":
                             crew.evaluate_flight(p, flight_no, message, sender), "VALIDATE",
                             "Store crew message as untrusted data, validate every crew member, hold departure "
                             "and stage reserve proposals if needed"),
    "submit_signoff_for_validation": (lambda p, **kw: maintenance.submit_signoff(p, **kw), "VALIDATE",
                                      "Record an immutable sign-off and run the 10 deterministic checks"),
    "verify_audit_trail": (lambda p, entity_ids: _verify_audit(entity_ids), "READ",
                           "Check that every critical entity has append-only audit events"),
    # STAGE (human decides later)
    "stage_gate_move": (lambda p, flight_no, gate, note=None: gate_approvals.stage_gate_move(p, flight_no, gate,
                                                                                               note=note), "STAGE",
                        "Stage a versioned gate-move proposal for controller approval"),
    "revalidate_affected_approvals": (lambda p, resources: gate_approvals.revalidate_affected(p, resources), "STAGE",
                                      "Mark approvals bound to changed resources STALE and re-stage"),
    # COMMIT (policy-permitted deterministic commits; the service re-validates inside its transaction)
    "create_rebooking_job": (lambda p, disrupted_flight, target_flight, idempotency_key=None:
                             rebooking.create_job(p, disrupted_flight, target_flight, idempotency_key), "COMMIT",
                             "Create the rebooking job: vulnerable priority transaction + batches of 10"),
    "run_rebooking_job": (lambda p, job_id, inject=None: rebooking.run_job(p, job_id, inject), "COMMIT",
                          "Process each batch in its own transaction; failed batch rolls back only itself"),
    "commit_rebooking_with_baggage": (lambda p, booking_ref, candidate_flight, idempotency_key=None, inject=None:
                                      baggage.commit_rebooking_with_baggage(p, booking_ref, candidate_flight,
                                                                            idempotency_key, inject=inject), "COMMIT",
                                      "Seat + bag plan + delivery note in ONE transaction"),
    "process_alert": (lambda p, text, source="OCC": journey.process_alert(p, text, source=source), "COMMIT",
                      "Round 3 alert journey: checks → injection screen → AI intake → validate → specialist"),
    # NOTIFY
    "compose_passenger_update": (lambda p, booking_ref: _compose_update(booking_ref), "NOTIFY",
                                 "Passenger wording from committed records only"),
}

# Capabilities that exist for HUMANS only (controller API) or outside SkyAssist. Listed so the UI can show them;
# none of them is in TOOLS, so no agent can ever reach them.
HUMAN_ONLY = {
    "approve_gate_move": "Controller decision (require_controller) bound to the reviewed snapshot hash",
    "execute_gate_move": "Controller only; compare-and-set on resource versions",
    "decide_crew_proposal": "Controller only; legality re-checked at execution",
    "decide_journey_approval": "Controller only; 15-minute expiry, safe default = no change",
    "retry_escalated_batch": "Controller only",
    "update_duty_limit": "Not possible from SkyAssist (immutable rule profiles, DB trigger)",
    "release_aircraft": "Outside SkyAssist — final release stays with authorised maintenance staff",
    "override_seat_inventory": "Not possible (PK + compare-and-set)",
}

AGENTS = {
    "flight_intel": {
        "name": "Flight Disruption Intelligence", "short": "FLIGHT INTELLIGENCE", "color": "violet",
        "responsibility": "Receives operational alerts, identifies affected flights and passengers, routes the "
                          "disruption to the right specialist.",
        "tools": ["process_alert", "get_flight", "list_affected_passengers", "departure_status", "gate_detail"],
        "never": ["approve or execute anything", "write operational records directly"],
    },
    "passenger_recovery": {
        "name": "Passenger Recovery", "short": "PASSENGER RECOVERY", "color": "cyan",
        "responsibility": "Prioritises vulnerable passengers (recorded needs only), prepares and commits "
                          "policy-permitted rebookings, escalates failed batches.",
        "tools": ["list_affected_passengers", "create_rebooking_job", "run_rebooking_job", "rebooking_report",
                  "baggage_feasibility", "commit_rebooking_with_baggage"],
        "never": ["override seat inventory", "retry an escalated batch (controller decision)"],
    },
    "crew_compliance": {
        "name": "Crew Compliance", "short": "CREW COMPLIANCE", "color": "amber",
        "responsibility": "Treats crew-channel text as untrusted data, requests deterministic duty validation, "
                          "searches reserves and stages proposals.",
        "tools": ["crew_board", "evaluate_flight_crew", "validate_crew_legality"],
        "never": ["modify duty counters or legal limits", "assign crew without controller approval"],
    },
    "maintenance": {
        "name": "Maintenance Intelligence", "short": "MAINTENANCE", "color": "red",
        "responsibility": "Submits sign-offs for Python validation, explains rejections, alerts maintenance "
                          "control.",
        "tools": ["submit_signoff_for_validation", "departure_status"],
        "never": ["issue maintenance release", "edit or delete a sign-off record"],
    },
    "baggage": {
        "name": "Baggage Coordination", "short": "BAGGAGE", "color": "amber",
        "responsibility": "Evaluates passenger–bag connections, finds a viable later bag flight, prepares the "
                          "delivery plan.",
        "tools": ["baggage_feasibility", "passenger_baggage_view"],
        "never": ["exceed bag capacity", "commit a seat without the bag plan"],
    },
    "gate_resource": {
        "name": "Gate and Resource", "short": "GATE CONTROL", "color": "cyan",
        "responsibility": "Analyses gate conflicts, checks state versions, stages gate moves for controller "
                          "approval.",
        "tools": ["gate_detail", "stage_gate_move", "revalidate_affected_approvals"],
        "never": ["assign an occupied gate", "execute a gate move", "execute a stale approval"],
    },
    "communication": {
        "name": "Passenger Communication", "short": "COMMUNICATION", "color": "white",
        "responsibility": "Explains rebooking, baggage and assistance status to passengers from committed "
                          "records (English; Hinglish handled by the v2 agent; Arabic extension point).",
        "tools": ["compose_passenger_update", "passenger_baggage_view"],
        "never": ["promise an outcome that is not committed"],
    },
    "safety_supervisor": {
        "name": "Safety and Audit Supervisor", "short": "SAFETY SUPERVISOR", "color": "green",
        "responsibility": "Enforces every agent's tool allowlist at runtime, rejects unauthorised calls, checks "
                          "that audit events exist. Does not replace Python validation.",
        "tools": ["verify_audit_trail", "departure_status"],
        "never": ["approve anything", "override a deterministic validation result"],
    },
}


def tool_catalog():
    return {name: {"kind": kind, "description": desc} for name, (_, kind, desc) in TOOLS.items()}
