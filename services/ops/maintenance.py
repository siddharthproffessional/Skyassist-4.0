"""U-4.3 — MAINTENANCE SIGN-OFF VALIDATION.

"OK" is a claim, not evidence. Every sign-off is stored immutably, then validated by Python against the licensed
roster, licence validity, aircraft type, task scope, aircraft registration, defect timeline, record integrity and
supporting evidence. An invalid sign-off keeps the aircraft blocked and alerts maintenance control. A valid one
clears only its own defect; final operational release stays with authorised personnel outside SkyAssist.
"""
import json
from datetime import datetime, timezone

from db import query, query_one, tx, utcnow
from services.ops.foundation import (OpsError, alert, audit, canonical_hash, new_id, outbox, policy, require_ops)

MODULE = "MAINTENANCE"
ACCEPTED_RESULTS = {"OK", "SERVICEABLE", "SATISFACTORY"}


def _epoch():
    return int(policy("demo.epoch", "1"))


def _hash(fields):
    return canonical_hash({k: fields[k] for k in ("engineer_id", "defect_id", "reg", "task_scope", "result",
                                                  "signed_at_utc", "evidence_ref")})


def submit_signoff(principal, engineer_id, defect_id, reg, task_scope, result, signed_at_utc, evidence_ref,
                   submitted_by=None):
    """Store the sign-off exactly as submitted (never rewritten), then validate it."""
    require_ops(principal)
    fields = {"engineer_id": (engineer_id or "").strip(), "defect_id": defect_id, "reg": reg,
              "task_scope": task_scope, "result": (result or "").strip().upper(), "signed_at_utc": signed_at_utc,
              "evidence_ref": evidence_ref}
    sid = new_id("SO")
    with tx() as con:
        con.execute("INSERT INTO maintenance_signoffs VALUES(?,?,?,?,?,?,?,?,?,'PENDING_VALIDATION',NULL,?,?,?)",
                    (sid, *fields.values(), _hash(fields), utcnow(), submitted_by or principal.display_name, _epoch()))
        audit(con, principal.display_name, MODULE, "SIGNOFF_SUBMITTED", "signoff", sid, new=fields)
    return validate_maintenance_signoff(principal, sid)


def run_checks(s):
    """Deterministic checks. Returns a list of {check, passed, detail}."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    eng = query_one("SELECT * FROM maintenance_engineers WHERE engineer_id=?", (s["engineer_id"],))
    d = query_one("SELECT * FROM aircraft_defects WHERE defect_id=?", (s["defect_id"],))
    ac = query_one("SELECT * FROM aircraft WHERE reg=?", (d["reg"] if d else s["reg"],))
    add("1 engineer exists", eng is not None, s["engineer_id"] + (" found" if eng else " is not a known engineer"))
    add("2 on trusted licensed roster", eng and eng["roster_status"] == "ON_ROSTER",
        (eng["roster_status"] if eng else "not on roster"))
    try:
        signed = datetime.fromisoformat(s["signed_at_utc"])
        signed_ok = True
    except (TypeError, ValueError):
        signed, signed_ok = None, False
    lic_ok = bool(eng and signed_ok and eng["licence_valid_from"] <= signed.date().isoformat() <= eng["licence_valid_to"])
    add("3 licence valid at sign-off", lic_ok,
        f"{eng['licence_no']} valid {eng['licence_valid_from']}–{eng['licence_valid_to']}" if eng else "no licence")
    types = json.loads(eng["authorised_types"]) if eng else []
    add("4 aircraft-type qualified", bool(ac and ac["aircraft_type"] in types),
        f"aircraft {ac['aircraft_type'] if ac else '?'}; engineer types {types}")
    scope = json.loads(eng["scope"]) if eng else []
    task = (d["defect_type"] if d else s["task_scope"])
    add("5 scope covers task", bool(task in scope and s["task_scope"] == task),
        f"task {s['task_scope']} for {task} defect; engineer scope {scope}")
    add("6 registration matches defect", bool(d and d["reg"] == s["reg"]),
        f"sign-off {s['reg']} vs defect {d['reg'] if d else '?'}")
    add("7 defect exists", d is not None, s["defect_id"] + (" open" if d and d["status"] == "OPEN" else
                                                           " " + (d["status"] if d else "not found")))
    after = bool(d and signed_ok and signed > datetime.fromisoformat(d["opened_at_utc"])
                 and signed <= datetime.now(timezone.utc))
    add("8 signed after defect opened", after,
        f"signed {s['signed_at_utc']} vs defect opened {d['opened_at_utc'] if d else '?'}")
    dup = query_one("SELECT signoff_id FROM maintenance_signoffs WHERE dataset_epoch=? AND signoff_id!=? AND "
                    "(record_hash=? OR (evidence_ref=? AND validation_status='VALID'))",
                    (s["dataset_epoch"], s["signoff_id"], s["record_hash"], s["evidence_ref"]))
    intact = _hash(s) == s["record_hash"]
    add("9 authentic, not reused or altered", intact and dup is None,
        ("record hash intact" if intact else "record hash mismatch") +
        (f"; duplicates {dup['signoff_id']}" if dup else ""))
    ev = query_one("SELECT * FROM maintenance_evidence WHERE evidence_ref=?", (s["evidence_ref"],))
    add("10 supporting evidence present", bool(ev and ev["defect_id"] == s["defect_id"]),
        (ev["description"] if ev else "no evidence record") + ("" if not ev or ev["defect_id"] == s["defect_id"]
                                                               else " (belongs to another defect)"))
    add("result is a recognised clearance", s["result"] in ACCEPTED_RESULTS,
        f"result {s['result']!r} (a result string alone is never sufficient)")
    return checks


def validate_maintenance_signoff(principal, signoff_id):
    require_ops(principal)
    s = query_one("SELECT * FROM maintenance_signoffs WHERE signoff_id=?", (signoff_id,))
    if s is None:
        raise OpsError("NO_SIGNOFF", "Sign-off not found.")
    checks = run_checks(s)
    valid = all(c["passed"] for c in checks)
    reasons = [c["detail"] for c in checks if not c["passed"]]
    actor = principal.display_name
    with tx() as con:
        for c in checks:
            con.execute("INSERT INTO maintenance_validation_events(signoff_id,check_name,passed,detail,created_at) "
                        "VALUES(?,?,?,?,?)", (signoff_id, c["check"], int(c["passed"]), c["detail"], utcnow()))
        cur = con.execute("UPDATE maintenance_signoffs SET validation_status=?, reasons=? WHERE signoff_id=? AND "
                          "validation_status='PENDING_VALIDATION'", ("VALID" if valid else "INVALID",
                                                                     json.dumps(reasons), signoff_id))
        if cur.rowcount != 1:
            raise OpsError("ALREADY_VALIDATED", "This sign-off was already validated.")
        if not valid:
            audit(con, actor, MODULE, "SIGNOFF_INVALID", "signoff", signoff_id, new={"reasons": reasons},
                  result="REJECTED", reason="Departure remains blocked")
            alert(con, MODULE, "CRITICAL", s["defect_id"], f"INVALID sign-off {signoff_id} on {s['reg']}",
                  "; ".join(reasons))
            outbox(con, "maintenance.signoff_invalid", {"signoff_id": signoff_id, "defect_id": s["defect_id"],
                                                         "reasons": reasons})
        else:
            con.execute("UPDATE aircraft_defects SET status='CLEARED', cleared_by_signoff=?, cleared_at=? WHERE "
                        "defect_id=? AND status='OPEN'", (signoff_id, utcnow(), s["defect_id"]))
            audit(con, actor, MODULE, "SIGNOFF_VALID", "signoff", signoff_id, result="ACCEPTED",
                  new={"defect": s["defect_id"], "status": "CLEARED"})
            remaining = con.execute("SELECT COUNT(*) n FROM aircraft_defects WHERE reg=? AND status='OPEN' AND "
                                    "restriction='NO_DEPARTURE'", (s["reg"],)).fetchone()["n"]
            if remaining == 0:
                for f in con.execute("SELECT flight_no FROM flight_ops WHERE aircraft_reg=?", (s["reg"],)).fetchall():
                    con.execute("UPDATE departure_holds SET status='CLEARED', cleared_at=?, cleared_by=? WHERE "
                                "flight_no=? AND hold_type='MAINTENANCE' AND status='ACTIVE'",
                                (utcnow(), f"validated sign-off {signoff_id}", f["flight_no"]))
                con.execute("UPDATE aircraft SET status='AWAITING_FINAL_RELEASE' WHERE reg=?", (s["reg"],))
                audit(con, actor, MODULE, "MAINTENANCE_RESTRICTION_LIFTED", "aircraft", s["reg"],
                      reason="No open NO_DEPARTURE defects; final operational release remains with authorised personnel")
            outbox(con, "maintenance.signoff_valid", {"signoff_id": signoff_id, "defect_id": s["defect_id"]})
    return {"signoff_id": signoff_id, "status": "VALID" if valid else "INVALID", "checks": checks, "reasons": reasons,
            "departure_blocked": departure_status_for_reg(s["reg"])["blocked"]}


def departure_status_for_reg(reg):
    defects = query("SELECT * FROM aircraft_defects WHERE reg=? AND status='OPEN' AND restriction='NO_DEPARTURE'", (reg,))
    return {"reg": reg, "blocked": bool(defects), "open_defects": defects}


def departure_status(flight_no):
    """Aggregates every hold. A cleared maintenance restriction is NOT a release to fly."""
    holds = query("SELECT * FROM departure_holds WHERE flight_no=? AND status='ACTIVE'", (flight_no,))
    fo = query_one("SELECT aircraft_reg FROM flight_ops WHERE flight_no=?", (flight_no,))
    ms = departure_status_for_reg(fo["aircraft_reg"]) if fo else {"blocked": False, "open_defects": []}
    blocked = bool(holds) or ms["blocked"]
    return {"flight_no": flight_no, "blocked": blocked, "holds": holds, "open_defects": ms["open_defects"],
            "label": "DEPARTURE BLOCKED" if blocked else "NO SKYASSIST HOLDS — final release by authorised personnel"}


def signoffs(defect_id=None):
    if defect_id:
        return query("SELECT * FROM maintenance_signoffs WHERE defect_id=? ORDER BY submitted_at DESC", (defect_id,))
    return query("SELECT * FROM maintenance_signoffs ORDER BY submitted_at DESC")


def validation_events(signoff_id):
    return query("SELECT * FROM maintenance_validation_events WHERE signoff_id=? ORDER BY id", (signoff_id,))
