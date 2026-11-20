"""U-4.2 — CREW DUTY LEGALITY (deterministic, fail-closed, message-proof).

* Crew-channel text is stored and flagged as untrusted DATA. It never changes a counter or a verdict.
* Duty limits live in duty_rule_profiles (immutable by trigger). Duty counters come only from the roster feed.
  Neither the LLM, the API nor the UI has a write path to them.
* Missing or unverified rules → UNKNOWN → departure stays blocked (fail closed).
* Controllers can approve a LEGAL reserve proposal; legality is re-checked at execution and an illegal candidate
  can never be approved.

The DEMO-FDP profile is SYNTHETIC demonstration data, not a real regulation.
"""
import json
import re

from db import query, query_one, tx, utcnow
from services.ops.foundation import (OpsError, alert, audit, new_id, outbox, require_controller, require_ops)

MODULE = "CREW"
DEMO_TODAY = "2026-11-20"
CLAIM_PATTERNS = {
    "EXTENSION_CLAIM": r"extend(ing)?\s+(the\s+)?duty|work\s+(another|an extra|extra)|agree",
    "APPROVAL_CLAIM": r"\bapproved?\b|authori[sz]ed|permission|supervisor|captain says",
    "OVERRIDE_ATTEMPT": r"ignore|override|bypass|skip\s+(the\s+)?check",
    "PRESSURE": r"push\s+(the\s+)?departure|go\s+now|just\s+dispatch",
}


def classify_message(body):
    t = (body or "").lower()
    return [k for k, p in CLAIM_PATTERNS.items() if re.search(p, t)]


def ingest_crew_message(principal, flight_no, sender, body, channel="CREW_CHANNEL"):
    """Log a crew message as untrusted data. Returns the stored record. Changes nothing else."""
    require_ops(principal)
    flags = classify_message(body)
    with tx() as con:
        cur = con.execute("INSERT INTO crew_messages(flight_no,channel,sender,body,flags,received_at) VALUES(?,?,?,?,?,?)",
                          (flight_no, channel, sender, body, json.dumps(flags), utcnow()))
        mid = cur.lastrowid
        audit(con, principal.display_name, MODULE, "CREW_MESSAGE_LOGGED", "crew_message", str(mid),
              new={"flight": flight_no, "flags": flags},
              reason="Treated as untrusted data; cannot change duty counters or legality")
    return {"msg_id": mid, "flags": flags, "treated_as": "UNTRUSTED_DATA"}


def _crew_snapshot(crew_id):
    c = query_one("SELECT * FROM crew_members WHERE crew_id=?", (crew_id,))
    d = query_one("SELECT * FROM crew_duty_records WHERE crew_id=?", (crew_id,))
    q = query("SELECT * FROM crew_qualifications WHERE crew_id=?", (crew_id,))
    return c, d, q


def validate_crew_legality(flight_no, crew_id, required_min=None, as_reserve=False):
    """Pure deterministic check. Verdict LEGAL / ILLEGAL / UNKNOWN with every check listed."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "result": ok, "detail": detail})

    fo = query_one("SELECT * FROM flight_ops WHERE flight_no=?", (flight_no,))
    ac = query_one("SELECT * FROM aircraft WHERE reg=?", (fo["aircraft_reg"],)) if fo else None
    c, d, quals = _crew_snapshot(crew_id)
    if required_min is None:
        required_min = fo["required_duty_min"] if fo else None
    add("1 identity", c is not None, f"{crew_id} {'found' if c else 'not on the crew roster'}")
    if c is None or fo is None or ac is None:
        add("data", None, "Flight, aircraft or crew data missing")
        return _verdict(flight_no, crew_id, checks, None, required_min, None)
    add("2 qualification record", bool(quals), ", ".join(f"{q['aircraft_type']} until {q['valid_until']}" for q in quals)
        or "no qualifications on file")
    q = next((x for x in quals if x["aircraft_type"] == ac["aircraft_type"]), None)
    add("3 aircraft-type qualification", bool(q) and q["valid_until"] >= DEMO_TODAY,
        f"needs {ac['aircraft_type']}: " + ("missing" if not q else
                                             ("valid" if q["valid_until"] >= DEMO_TODAY else f"expired {q['valid_until']}")))
    add("4 availability", c["availability"] != "UNAVAILABLE", f"{c['roster_status']} / {c['availability']}")
    prof = query_one("SELECT * FROM duty_rule_profiles WHERE profile_id=?", (fo["duty_profile_id"],))
    if prof is None or not prof["verified"] or prof["max_duty_min"] is None:
        add("5 applicable duty rules", None, f"Profile {fo['duty_profile_id']} is not configured/verified — fail closed")
        return _verdict(flight_no, crew_id, checks, prof, required_min, None)
    add("5 applicable duty rules", True, f"{prof['profile_id']}: {prof['label']} (source: {prof['source']})")
    if d is None:
        add("6 duty record", None, "No duty record from the roster feed — fail closed")
        return _verdict(flight_no, crew_id, checks, prof, required_min, None)
    if as_reserve or c["availability"] == "AVAILABLE":
        add("6 rest requirement", d["rest_since_min"] >= prof["min_rest_min"],
            f"rested {d['rest_since_min']} min, needs {prof['min_rest_min']} min")
        remaining = prof["max_duty_min"]
    else:
        add("6 rest requirement", True, "on duty — rest check applies before the next duty")
        remaining = prof["max_duty_min"] - d["elapsed_min"]
    add("7 projected duty", remaining >= required_min if required_min is not None else None,
        f"remaining {remaining} min vs required {required_min} min")
    return _verdict(flight_no, crew_id, checks, prof, required_min, remaining)


def _verdict(flight_no, crew_id, checks, prof, required, remaining):
    if any(c["result"] is False for c in checks):
        v = "ILLEGAL"
    elif any(c["result"] is None for c in checks):
        v = "UNKNOWN"
    else:
        v = "LEGAL"
    return {"flight_no": flight_no, "crew_id": crew_id, "verdict": v, "checks": checks,
            "required_min": required, "remaining_min": remaining,
            "profile": dict(prof) if prof else None}


def evaluate_flight(principal, flight_no, message=None, sender="crew channel"):
    """Validate every assigned crew member; block departure and search reserves when anyone is not LEGAL."""
    require_ops(principal)
    actor = principal.display_name
    msg = ingest_crew_message(principal, flight_no, sender, message) if message else None
    before = {r["crew_id"]: dict(r) for r in query("SELECT * FROM crew_duty_records")}
    crew = query("SELECT * FROM flight_crew WHERE flight_no=? AND status='ASSIGNED'", (flight_no,))
    results = [validate_crew_legality(flight_no, c["crew_id"]) for c in crew]
    blocked = [r for r in results if r["verdict"] != "LEGAL"]
    proposals = []
    with tx() as con:
        audit(con, actor, MODULE, "CREW_LEGALITY_EVALUATED", "flight", flight_no,
              new={r["crew_id"]: r["verdict"] for r in results}, result="BLOCKED" if blocked else "LEGAL")
        if blocked:
            con.execute("INSERT OR IGNORE INTO departure_holds(flight_no,hold_type,reason,status,created_at) "
                        "VALUES(?,?,?,'ACTIVE',?)", (flight_no, "CREW",
                                                    "; ".join(f"{r['crew_id']} {r['verdict']}" for r in blocked), utcnow()))
            alert(con, MODULE, "HIGH", flight_no, f"Crew legality: departure of {flight_no} blocked",
                  "; ".join(f"{r['crew_id']}: {r['verdict']} (remaining {r['remaining_min']} vs required "
                            f"{r['required_min']} min)" for r in blocked))
            outbox(con, "crew.violation", {"flight": flight_no, "blocked": [r["crew_id"] for r in blocked]})
    for r in blocked:
        if r["verdict"] == "ILLEGAL":
            role = query_one("SELECT role FROM flight_crew WHERE flight_no=? AND crew_id=?", (flight_no, r["crew_id"]))
            proposals.append(search_reserves(principal, flight_no, r["crew_id"], role["role"], r["required_min"]))
    after = {r["crew_id"]: dict(r) for r in query("SELECT * FROM crew_duty_records")}
    return {"flight_no": flight_no, "message": msg, "results": results, "departure_blocked": bool(blocked),
            "reserve_search": proposals, "duty_counters_unchanged": before == after}


def search_reserves(principal, flight_no, replace_crew_id, role, required_min):
    require_ops(principal)
    candidates = query("SELECT crew_id FROM crew_members WHERE role=? AND roster_status='RESERVE' AND "
                       "availability='AVAILABLE' ORDER BY crew_id", (role,))
    evaluated = [validate_crew_legality(flight_no, c["crew_id"], required_min, as_reserve=True) for c in candidates]
    legal = sorted([e for e in evaluated if e["verdict"] == "LEGAL"], key=lambda e: -(e["remaining_min"] or 0))
    proposal = None
    with tx() as con:
        audit(con, principal.display_name, MODULE, "RESERVE_SEARCH", "flight", flight_no,
              new={e["crew_id"]: e["verdict"] for e in evaluated},
              result=f"{len(legal)} legal candidate(s)")
        if legal:
            existing = con.execute("SELECT proposal_id FROM crew_assignment_proposals WHERE flight_no=? AND "
                                   "replace_crew_id=? AND status='PENDING_APPROVAL'", (flight_no, replace_crew_id)).fetchone()
            if existing:
                proposal = existing["proposal_id"]
            else:
                best = legal[0]
                proposal = new_id("CRP")
                con.execute("INSERT INTO crew_assignment_proposals VALUES(?,?,?,?,?,?,?,?,'PENDING_APPROVAL',?,NULL,NULL,NULL)",
                            (proposal, flight_no, replace_crew_id, best["crew_id"], role, required_min,
                             best["remaining_min"], json.dumps(best), utcnow()))
                audit(con, principal.display_name, MODULE, "RESERVE_PROPOSAL_STAGED", "crew_proposal", proposal,
                      new={"replace": replace_crew_id, "candidate": best["crew_id"]}, reason="Awaiting controller approval")
                outbox(con, "crew.proposal_staged", {"proposal_id": proposal, "flight": flight_no})
        else:
            alert(con, MODULE, "CRITICAL", flight_no, f"No legal crew available for {flight_no}",
                  "Departure remains blocked; controller escalation required.")
    return {"replace": replace_crew_id, "evaluated": evaluated, "proposal_id": proposal}


def decide_proposal(principal, proposal_id, approve, note=""):
    """Controller approval of a legal proposal. Legality is re-validated at execution, inside the transaction."""
    require_controller(principal)
    p = query_one("SELECT * FROM crew_assignment_proposals WHERE proposal_id=?", (proposal_id,))
    if p is None:
        raise OpsError("NO_PROPOSAL", "Proposal not found.")
    fresh = validate_crew_legality(p["flight_no"], p["candidate_crew_id"], p["required_min"], as_reserve=True)
    refused = False
    with tx() as con:
        cur = con.execute("SELECT status FROM crew_assignment_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if cur["status"] != "PENDING_APPROVAL":
            raise OpsError("NOT_PENDING", f"Proposal is {cur['status']}.")
        if not approve:
            con.execute("UPDATE crew_assignment_proposals SET status='REJECTED', decided_by=?, decided_at=?, note=? "
                        "WHERE proposal_id=?", (principal.display_name, utcnow(), note, proposal_id))
            audit(con, principal.display_name, MODULE, "PROPOSAL_REJECTED", "crew_proposal", proposal_id, reason=note)
            return {"status": "REJECTED"}
        if fresh["verdict"] != "LEGAL":
            con.execute("UPDATE crew_assignment_proposals SET status='REFUSED_ILLEGAL', decided_by=?, decided_at=?, "
                        "note=? WHERE proposal_id=?", (principal.display_name, utcnow(),
                                                         "Re-validation failed at execution", proposal_id))
            audit(con, principal.display_name, MODULE, "APPROVAL_REFUSED_ILLEGAL", "crew_proposal", proposal_id,
                  new=fresh, result="REFUSED", reason="Controller approval cannot make an illegal assignment legal")
            refused = True
    if refused:   # raised only after the refusal record has been committed
        raise OpsError("ILLEGAL_ASSIGNMENT", "The candidate is not legal at execution time; approval refused.", fresh)
    with tx() as con:
        if con.execute("SELECT status FROM crew_assignment_proposals WHERE proposal_id=?",
                       (proposal_id,)).fetchone()["status"] != "PENDING_APPROVAL":
            raise OpsError("NOT_PENDING", "Proposal was decided concurrently.")
        con.execute("UPDATE flight_crew SET status='REPLACED' WHERE flight_no=? AND crew_id=?",
                    (p["flight_no"], p["replace_crew_id"]))
        con.execute("INSERT OR REPLACE INTO flight_crew VALUES(?,?,?,'ASSIGNED',?)",
                    (p["flight_no"], p["candidate_crew_id"], p["role"], utcnow()))
        con.execute("UPDATE crew_members SET availability='ON_DUTY' WHERE crew_id=?", (p["candidate_crew_id"],))
        con.execute("UPDATE crew_assignment_proposals SET status='APPROVED_EXECUTED', decided_by=?, decided_at=?, note=? "
                    "WHERE proposal_id=?", (principal.display_name, utcnow(), note, proposal_id))
        audit(con, principal.display_name, MODULE, "CREW_ASSIGNMENT_EXECUTED", "flight", p["flight_no"],
              old={"crew": p["replace_crew_id"]}, new={"crew": p["candidate_crew_id"], "validation": fresh["verdict"]},
              result="COMMITTED")
    # re-check the whole crew; clear the hold only when every assigned member is LEGAL
    crew = query("SELECT crew_id FROM flight_crew WHERE flight_no=? AND status='ASSIGNED'", (p["flight_no"],))
    verdicts = {c["crew_id"]: validate_crew_legality(p["flight_no"], c["crew_id"])["verdict"] for c in crew}
    if all(v == "LEGAL" for v in verdicts.values()):
        with tx() as con:
            con.execute("UPDATE departure_holds SET status='CLEARED', cleared_at=?, cleared_by=? WHERE flight_no=? AND "
                        "hold_type='CREW' AND status='ACTIVE'", (utcnow(), principal.display_name, p["flight_no"]))
            audit(con, principal.display_name, MODULE, "CREW_HOLD_CLEARED", "flight", p["flight_no"], new=verdicts)
    return {"status": "APPROVED_EXECUTED", "crew_verdicts": verdicts}


def stage_manual_assignment(principal, flight_no, replace_crew_id, candidate_crew_id):
    """A controller may only stage a candidate that passes validation."""
    require_controller(principal)
    role = query_one("SELECT role FROM flight_crew WHERE flight_no=? AND crew_id=?", (flight_no, replace_crew_id))
    fo = query_one("SELECT required_duty_min FROM flight_ops WHERE flight_no=?", (flight_no,))
    v = validate_crew_legality(flight_no, candidate_crew_id, fo["required_duty_min"], as_reserve=True)
    if v["verdict"] != "LEGAL":
        from services.ops.foundation import audit_now
        audit_now(principal.display_name, MODULE, "MANUAL_ASSIGNMENT_REFUSED", entity_type="flight",
                  entity_id=flight_no, new=v, result="REFUSED")
        raise OpsError("ILLEGAL_ASSIGNMENT", f"{candidate_crew_id} is {v['verdict']} for {flight_no}.", v)
    pid = new_id("CRP")
    with tx() as con:
        con.execute("INSERT INTO crew_assignment_proposals VALUES(?,?,?,?,?,?,?,?,'PENDING_APPROVAL',?,NULL,NULL,NULL)",
                    (pid, flight_no, replace_crew_id, candidate_crew_id, role["role"], fo["required_duty_min"],
                     v["remaining_min"], json.dumps(v), utcnow()))
        audit(con, principal.display_name, MODULE, "RESERVE_PROPOSAL_STAGED", "crew_proposal", pid)
    return pid


def update_duty_limit(principal, *_, **__):
    """There is deliberately no way to change duty limits or counters from SkyAssist."""
    from services.ops.foundation import audit_now
    audit_now(getattr(principal, "display_name", "unknown"), MODULE, "DUTY_LIMIT_CHANGE_REFUSED", result="REFUSED",
              reason="Duty limits/counters are read-only in SkyAssist")
    raise OpsError("READ_ONLY", "Duty limits and counters are read-only. They come only from the roster system.")


def apply_synthetic_roster_feed(crew_id, elapsed_min=None, rest_since_min=None, availability=None):
    """SIMULATOR ONLY: stands in for the airline's roster system feed (clearly labelled synthetic).
    Not reachable from the AI agent, the API or any coordinator control."""
    with tx() as con:
        old = con.execute("SELECT * FROM crew_duty_records WHERE crew_id=?", (crew_id,)).fetchone()
        if elapsed_min is not None:
            con.execute("UPDATE crew_duty_records SET elapsed_min=?, recorded_at=?, source='SYNTHETIC roster feed' "
                        "WHERE crew_id=?", (elapsed_min, utcnow(), crew_id))
        if rest_since_min is not None:
            con.execute("UPDATE crew_duty_records SET rest_since_min=?, recorded_at=? WHERE crew_id=?",
                        (rest_since_min, utcnow(), crew_id))
        if availability:
            con.execute("UPDATE crew_members SET availability=? WHERE crew_id=?", (availability, crew_id))
        audit(con, "synthetic-roster-feed", "SIMULATOR", "ROSTER_FEED_UPDATE", "crew", crew_id,
              old=dict(old) if old else None,
              new={"elapsed_min": elapsed_min, "rest_since_min": rest_since_min, "availability": availability})


def crew_board(flight_no):
    rows = []
    for c in query("SELECT fc.*, cm.name FROM flight_crew fc JOIN crew_members cm USING(crew_id) WHERE flight_no=? "
                   "ORDER BY fc.status, fc.role", (flight_no,)):
        v = validate_crew_legality(flight_no, c["crew_id"]) if c["status"] == "ASSIGNED" else None
        rows.append({**c, "validation": v})
    return rows


def proposals(flight_no=None):
    if flight_no:
        return query("SELECT * FROM crew_assignment_proposals WHERE flight_no=? ORDER BY created_at DESC", (flight_no,))
    return query("SELECT * FROM crew_assignment_proposals ORDER BY created_at DESC")
