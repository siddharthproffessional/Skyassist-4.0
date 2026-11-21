"""U-4.5 — STALE APPROVAL PROTECTION (versioned state, compare-and-set execution).

An approval authorises exactly the state the controller reviewed: the action, the flight, the target gate and the
resource versions in the snapshot. At execution the versions are re-read inside a BEGIN IMMEDIATE transaction;
any mismatch refuses the action, marks the approval STALE and stages a fresh proposal for the controller.
"""
import json
from datetime import datetime, timedelta, timezone

import tools
from db import query, query_one, tx, utcnow
from services.ops.foundation import (OpsError, alert, audit, canonical_hash, new_id, outbox, policy,
                                     require_controller, require_ops, version_of, bump)

MODULE = "GATES"


def norm_gate(g):
    n = tools.normalize_gate(g)
    if not n or not query_one("SELECT 1 AS x FROM gates WHERE gate=?", (n,)):
        raise OpsError("UNKNOWN_GATE", f"Unknown gate {g!r}.")
    return n


def gate_occupants(con, gate):
    return [r["flight_no"] for r in con.execute(
        "SELECT flight_no FROM flights WHERE gate=? AND direction='DEPARTURE' AND status!='CANCELLED' "
        "ORDER BY flight_no", (gate,))]


def _snapshot(con, flight_no, gate):
    f = con.execute("SELECT flight_no, gate, status FROM flights WHERE flight_no=?", (flight_no,)).fetchone()
    if f is None:
        raise OpsError("UNKNOWN_FLIGHT", f"{flight_no} not found.")
    occ = gate_occupants(con, gate)
    snap = {"action": "GATE_MOVE", "flight": flight_no, "flight_current_gate": f["gate"], "flight_status": f["status"],
            "target_gate": gate, "target_occupants": occ,
            "versions": {f"GATE:{gate}": version_of(con, f"GATE:{gate}"),
                         f"FLIGHT:{flight_no}": version_of(con, f"FLIGHT:{flight_no}")}}
    return snap


def stage_gate_move(principal, flight_no, gate, parent_id=None, note=None):
    require_ops(principal)
    gate = norm_gate(gate)
    ttl = int(policy("approvals.gate_move_ttl_min", "30"))
    with tx() as con:
        snap = _snapshot(con, flight_no, gate)
        if snap["target_occupants"]:
            raise OpsError("GATE_OCCUPIED", f"Gate {gate} is assigned to {', '.join(snap['target_occupants'])}.")
        aid = new_id("APR")
        exp = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).isoformat(timespec="seconds")
        con.execute("INSERT INTO approval_requests VALUES(?,?,?,?,?,?,?,?,'PENDING',?,?,NULL,NULL,NULL,?,NULL,NULL,?)",
                    (aid, "GATE_MOVE", flight_no, f"GATE:{gate}",
                     json.dumps({"flight": flight_no, "gate": gate}), json.dumps(snap["versions"]), json.dumps(snap),
                     canonical_hash(snap), principal.display_name, utcnow(), exp, parent_id))
        audit(con, principal.display_name, MODULE, "APPROVAL_STAGED", "approval", aid, new=snap, reason=note)
        outbox(con, "approval.staged", {"approval_id": aid, "flight": flight_no, "gate": gate})
    return get(aid)


def approve(principal, approval_id, snapshot_hash_seen, note=""):
    """Human decision. The controller must have reviewed the exact snapshot (hash) that is stored."""
    require_controller(principal)
    with tx() as con:
        a = con.execute("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,)).fetchone()
        if a is None:
            raise OpsError("NO_APPROVAL", "Approval request not found.")
        if snapshot_hash_seen != a["snapshot_hash"]:
            raise OpsError("SNAPSHOT_MISMATCH", "The reviewed snapshot does not match the stored request.")
        cur = con.execute("UPDATE approval_requests SET status='APPROVED', decided_by=?, decided_at=? "
                          "WHERE approval_id=? AND status='PENDING'", (principal.display_name, utcnow(), approval_id))
        if cur.rowcount != 1:
            raise OpsError("NOT_PENDING", f"Approval is {a['status']}, not pending.")
        con.execute("INSERT INTO approval_decisions(approval_id,decision,actor,reason,snapshot_hash_seen,created_at) "
                    "VALUES(?,?,?,?,?,?)", (approval_id, "APPROVED", principal.display_name, note, snapshot_hash_seen,
                                            utcnow()))
        audit(con, principal.display_name, MODULE, "APPROVAL_GRANTED", "approval", approval_id,
              old="PENDING", new="APPROVED", reason=note)
    return get(approval_id)


def reject(principal, approval_id, note=""):
    require_controller(principal)
    with tx() as con:
        cur = con.execute("UPDATE approval_requests SET status='REJECTED', decided_by=?, decided_at=? "
                          "WHERE approval_id=? AND status='PENDING'", (principal.display_name, utcnow(), approval_id))
        if cur.rowcount != 1:
            raise OpsError("NOT_PENDING", "Only pending approvals can be rejected.")
        con.execute("INSERT INTO approval_decisions(approval_id,decision,actor,reason,created_at) VALUES(?,?,?,?,?)",
                    (approval_id, "REJECTED", principal.display_name, note, utcnow()))
        audit(con, principal.display_name, MODULE, "APPROVAL_REJECTED", "approval", approval_id, reason=note)
    return get(approval_id)


def _nearest_free_gate(con, gate):
    conc, num = gate[0], int(gate[1:])
    rows = con.execute("SELECT gate, number FROM gates WHERE concourse=? ORDER BY ABS(number-?), number",
                       (conc, num)).fetchall()
    for r in rows:
        if r["gate"] != gate and not gate_occupants(con, r["gate"]):
            return r["gate"]
    return None


def _mark_stale_and_restage(con, a, reason, actor):
    con.execute("UPDATE approval_requests SET status='STALE', stale_reason=? WHERE approval_id=? AND status IN "
                "('APPROVED','PENDING')", (reason, a["approval_id"]))
    audit(con, actor, MODULE, "APPROVAL_STALE", "approval", a["approval_id"], old=a["status"], new="STALE",
          reason=reason, result="REFUSED")
    payload = json.loads(a["action_payload"])
    gate = payload["gate"]
    target = gate if not gate_occupants(con, gate) else _nearest_free_gate(con, gate)
    new_aid = None
    if target:
        snap = _snapshot(con, a["flight_no"], target)
        new_aid = new_id("APR")
        exp = (datetime.now(timezone.utc) + timedelta(minutes=int(policy("approvals.gate_move_ttl_min", "30"))))
        con.execute("INSERT INTO approval_requests VALUES(?,?,?,?,?,?,?,?,'PENDING',?,?,NULL,NULL,NULL,?,NULL,NULL,?)",
                    (new_aid, "GATE_MOVE", a["flight_no"], f"GATE:{target}",
                     json.dumps({"flight": a["flight_no"], "gate": target}), json.dumps(snap["versions"]),
                     json.dumps(snap), canonical_hash(snap), "SkyAssist (re-staged)", utcnow(),
                     exp.isoformat(timespec="seconds"), a["approval_id"]))
        con.execute("UPDATE approval_requests SET superseded_by=? WHERE approval_id=?", (new_aid, a["approval_id"]))
        audit(con, actor, MODULE, "APPROVAL_RESTAGED", "approval", new_aid, new=snap,
              reason=f"Fresh proposal after stale approval {a['approval_id']}")
    alert(con, MODULE, "HIGH", a["approval_id"], f"Stale approval refused for {a['flight_no']}",
          reason + (f" New proposal {new_aid} (gate {target}) needs a fresh decision." if new_aid else
                    " No free gate found — controller action required."))
    outbox(con, "approval.stale", {"approval_id": a["approval_id"], "new_approval_id": new_aid, "reason": reason})
    return new_aid


def execute(principal, approval_id, flight_no=None, gate=None):
    """Execute an approved gate move only if the reviewed state still holds. Atomic compare-and-set."""
    require_controller(principal)
    actor = principal.display_name
    with tx() as con:
        a = con.execute("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,)).fetchone()
        if a is None:
            raise OpsError("NO_APPROVAL", "Approval request not found.")
        payload = json.loads(a["action_payload"])
        if (flight_no and flight_no != a["flight_no"]) or (gate and tools.normalize_gate(gate) != payload["gate"]):
            audit(con, actor, MODULE, "EXECUTION_REFUSED", "approval", approval_id, result="REFUSED",
                  reason="Target substitution: approval is bound to a different flight/gate")
            refused = {"status": "REFUSED", "code": "TARGET_MISMATCH",
                       "reason": f"This approval only authorises {a['flight_no']} → {payload['gate']}."}
        elif a["status"] == "EXECUTED" or con.execute("SELECT 1 FROM operational_actions WHERE approval_id=?",
                                                      (approval_id,)).fetchone():
            refused = {"status": "REFUSED", "code": "ALREADY_EXECUTED", "reason": "This approval was already used."}
        elif a["status"] != "APPROVED":
            refused = {"status": "REFUSED", "code": f"NOT_APPROVED_{a['status']}",
                       "reason": f"Approval is {a['status']}; it cannot be executed."}
        elif datetime.fromisoformat(a["expires_at"]) < datetime.now(timezone.utc):
            con.execute("UPDATE approval_requests SET status='EXPIRED' WHERE approval_id=?", (approval_id,))
            audit(con, actor, MODULE, "APPROVAL_EXPIRED", "approval", approval_id, result="REFUSED")
            refused = {"status": "REFUSED", "code": "EXPIRED", "reason": "The approval has expired."}
        else:
            refused = None
            expected = json.loads(a["expected_versions"])
            current = {rid: version_of(con, rid) for rid in expected}
            snap = json.loads(a["snapshot"])
            occ = gate_occupants(con, payload["gate"])
            fl = con.execute("SELECT gate FROM flights WHERE flight_no=?", (a["flight_no"],)).fetchone()
            problems = [f"{rid}: approved at v{expected[rid]}, now v{current[rid]}" for rid in expected
                        if expected[rid] != current[rid]]
            if occ:
                problems.append(f"Gate {payload['gate']} is now assigned to {', '.join(occ)}")
            if fl["gate"] != snap["flight_current_gate"]:
                problems.append(f"{a['flight_no']} moved from {snap['flight_current_gate']} to {fl['gate']}")
            if problems:
                reason = "STALE APPROVAL — the operational state changed after review: " + "; ".join(problems)
                new_aid = _mark_stale_and_restage(con, a, reason, actor)
                refused = {"status": "STALE", "code": "VERSION_MISMATCH", "reason": reason, "problems": problems,
                           "new_approval_id": new_aid}
            else:
                old_gate = fl["gate"]
                con.execute("UPDATE flights SET previous_gate=gate, gate=?, status=CASE WHEN status IN "
                            "('ON_TIME','GATE_CHANGED') THEN 'GATE_CHANGED' ELSE status END WHERE flight_no=?",
                            (payload["gate"], a["flight_no"]))
                for rid in (f"GATE:{payload['gate']}", f"GATE:{old_gate}", f"FLIGHT:{a['flight_no']}"):
                    bump(con, rid, event=f"GATE_MOVE {approval_id}")
                con.execute("INSERT INTO operational_actions VALUES(?,?,?,?,?,?)",
                            (new_id("ACT"), approval_id, "GATE_MOVE", actor, utcnow(),
                             json.dumps({"from": old_gate, "to": payload["gate"]})))
                con.execute("UPDATE approval_requests SET status='EXECUTED', executed_at=? WHERE approval_id=?",
                            (utcnow(), approval_id))
                audit(con, actor, MODULE, "GATE_MOVE_EXECUTED", "flight", a["flight_no"], old={"gate": old_gate},
                      new={"gate": payload["gate"]}, txn_id=approval_id, result="COMMITTED")
                for p in con.execute("SELECT booking_ref FROM passengers WHERE outbound=?", (a["flight_no"],)):
                    con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) "
                                "VALUES(?,?,'GATE_CHANGE',?,?)", (p["booking_ref"], None,
                                                                  f"Gate change: {a['flight_no']} now departs from "
                                                                  f"Gate {payload['gate']} (was {old_gate}).", utcnow()))
                outbox(con, "gate.changed", {"flight": a["flight_no"], "from": old_gate, "to": payload["gate"],
                                             "resources": [f"GATE:{payload['gate']}", f"GATE:{old_gate}"]})
                return {"status": "EXECUTED", "flight": a["flight_no"], "from": old_gate, "to": payload["gate"]}
    if refused and refused["status"] == "REFUSED":
        from services.ops.foundation import audit_now
        audit_now(actor, MODULE, "EXECUTION_REFUSED", entity_type="approval", entity_id=approval_id,
                  reason=refused["reason"], result="REFUSED")
    return refused


def assign_gate_direct(principal, flight_no, gate, reason="Operational gate assignment"):
    """An operational state change (e.g. another flight receives the gate). Versioned and audited."""
    require_ops(principal)
    gate = norm_gate(gate)
    with tx() as con:
        occ = gate_occupants(con, gate)
        if occ and occ != [flight_no]:
            raise OpsError("GATE_OCCUPIED", f"Gate {gate} is assigned to {', '.join(occ)}.")
        fl = con.execute("SELECT gate FROM flights WHERE flight_no=?", (flight_no,)).fetchone()
        if fl is None:
            raise OpsError("UNKNOWN_FLIGHT", f"{flight_no} not found.")
        con.execute("UPDATE flights SET previous_gate=gate, gate=?, status=CASE WHEN status IN ('ON_TIME',"
                    "'GATE_CHANGED') THEN 'GATE_CHANGED' ELSE status END WHERE flight_no=?", (gate, flight_no))
        changed = [f"GATE:{gate}", f"GATE:{fl['gate']}", f"FLIGHT:{flight_no}"]
        for rid in changed:
            bump(con, rid, event=f"ASSIGN {flight_no}->{gate}")
        audit(con, principal.display_name, MODULE, "GATE_ASSIGNED", "flight", flight_no, old={"gate": fl["gate"]},
              new={"gate": gate}, reason=reason, result="COMMITTED")
        outbox(con, "state.changed", {"resources": changed, "reason": reason})
    return changed


def revalidate_affected(principal, resource_ids):
    """Workflow E: after a state change, mark every approval bound to a changed resource STALE and re-stage."""
    require_ops(principal)
    out = []
    with tx() as con:
        for a in con.execute("SELECT * FROM approval_requests WHERE status IN ('PENDING','APPROVED')").fetchall():
            exp = json.loads(a["expected_versions"])
            stale = [rid for rid in exp if rid in resource_ids and version_of(con, rid) != exp[rid]]
            if stale:
                reason = "STALE APPROVAL — state changed: " + ", ".join(
                    f"{r} now v{version_of(con, r)} (approved at v{exp[r]})" for r in stale)
                out.append({"approval_id": a["approval_id"], "new_approval_id":
                            _mark_stale_and_restage(con, a, reason, principal.display_name)})
    return out


def get(approval_id):
    r = query_one("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,))
    if r:
        r["snapshot_dict"] = json.loads(r["snapshot"])
        r["payload_dict"] = json.loads(r["action_payload"])
    return r


def approvals(statuses=None):
    if statuses:
        q = ",".join("?" * len(statuses))
        return query(f"SELECT * FROM approval_requests WHERE status IN ({q}) ORDER BY requested_at DESC", statuses)
    return query("SELECT * FROM approval_requests ORDER BY requested_at DESC")


def gate_board(concourse=None):
    rows = query("SELECT g.gate, g.concourse, (SELECT GROUP_CONCAT(flight_no) FROM flights f WHERE f.gate=g.gate AND "
                 "f.direction='DEPARTURE' AND f.status!='CANCELLED') AS occupants, "
                 "(SELECT version FROM resource_versions v WHERE v.resource_id='GATE:'||g.gate) AS version "
                 "FROM gates g " + ("WHERE g.concourse=? " if concourse else "") + "ORDER BY g.gate",
                 (concourse,) if concourse else ())
    return rows
