"""U-4.1 — VULNERABLE PASSENGERS FIRST, IN THEIR OWN TRANSACTION.

Sequence (exactly as the OCC policy requires):
  1 retrieve affected passengers   2 validate bookings   3 separate vulnerable (recorded needs only)
  4 one dedicated PRIORITY transaction   5 commit it   6 partition the rest into batches of 10 (last may be smaller)
  7 process every batch in its OWN transaction   8 a failed batch rolls back only itself
  9 retry with fresh seat availability   10 escalate to the controller when retries are exhausted
  11 keep processing independent batches   12 produce a complete report

There is never one transaction around the whole job, so a later failure can never undo earlier commits.
"""
import json

import tools
from db import query, query_one, tx, utcnow
from services.ops import baggage
from services.ops.foundation import (OpsError, alert, audit, new_id, outbox, policy, require_controller,
                                     require_ops)

MODULE = "REBOOKING"
BATCH_STATES = ["CREATED", "PENDING", "PROCESSING", "COMMITTED", "FAILED", "ROLLED_BACK", "RETRY_PENDING",
                "RETRYING", "ESCALATED", "COMPLETED"]


def _set_batch(con, batch_id, status, actor, **extra):
    old = con.execute("SELECT status FROM rebooking_batches WHERE batch_id=?", (batch_id,)).fetchone()
    sets = ", ".join(f"{k}=?" for k in extra)
    con.execute(f"UPDATE rebooking_batches SET status=?{', ' + sets if sets else ''} WHERE batch_id=?",
                (status, *extra.values(), batch_id))
    audit(con, actor, MODULE, f"BATCH_{status}", "rebooking_batch", batch_id, old=old["status"] if old else None,
          new=status, reason=extra.get("last_error"))


def classify(needs, vulnerable_codes):
    return bool(set(needs or []) & set(vulnerable_codes))


def create_job(principal, disrupted_flight, target_flight, idempotency_key=None, exclude_refs=()):
    """Steps 1–6. Idempotent on idempotency_key (a duplicate webhook returns the same job)."""
    require_ops(principal)
    if idempotency_key:
        prev = query_one("SELECT job_id FROM rebooking_jobs WHERE idem_key=?", (idempotency_key,))
        if prev:
            return prev["job_id"]
    vulnerable_codes = policy("rebooking.vulnerable_needs", ["WCHR", "UMNR", "ELDERLY"], as_json=True)
    size = int(policy("rebooking.batch_size", "10"))
    target = tools.get_flight_and_gate_status(target_flight)
    if not target.get("found") or target["status"] == "CANCELLED":
        raise OpsError("BAD_TARGET", f"{target_flight} is not an operating flight.")
    affected = [p for p in query("SELECT * FROM passengers WHERE outbound=? ORDER BY booking_ref", (disrupted_flight,))
                if p["booking_ref"] not in set(exclude_refs)]  # excluded = handled elsewhere (e.g. paused for approval)
    if not affected:
        raise OpsError("NO_PASSENGERS", f"No passengers are booked on {disrupted_flight}.")
    valid, invalid = [], []
    for p in affected:
        inb = tools.get_flight_and_gate_status(p["inbound"]) if p["inbound"] else {"found": False}
        (valid if inb.get("found") else invalid).append(p)
    vul = [p for p in valid if classify(json.loads(p["needs"]), vulnerable_codes)]
    gen = [p for p in valid if p not in vul]
    job_id = new_id("JOB")
    with tx() as con:
        con.execute("INSERT INTO rebooking_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (job_id, disrupted_flight, target_flight, "CREATED", len(valid), len(vul),
                     principal.display_name, utcnow(), None, None, idempotency_key))
        batches = [("PRIORITY", 0, vul)] + [("GENERAL", i + 1, gen[i * size:(i + 1) * size])
                                            for i in range((len(gen) + size - 1) // size)]
        for kind, seq, members in batches:
            if not members:
                continue
            bid = f"{job_id}-{'P' if kind == 'PRIORITY' else 'B'}{seq}"
            con.execute("INSERT INTO rebooking_batches(batch_id,job_id,seq,kind,status,passenger_count) "
                        "VALUES(?,?,?,?,'CREATED',?)", (bid, job_id, seq, kind, len(members)))
            for i, p in enumerate(members):
                con.execute("INSERT INTO rebooking_batch_items VALUES(?,?,?,'PENDING',NULL,NULL)",
                            (bid, p["booking_ref"], i))
            audit(con, principal.display_name, MODULE, "BATCH_CREATED", "rebooking_batch", bid,
                  new={"kind": kind, "passengers": len(members),
                       "vulnerable_needs": [json.loads(p["needs"]) for p in members] if kind == "PRIORITY" else None})
        for p in invalid:
            audit(con, principal.display_name, MODULE, "PASSENGER_EXCLUDED", "booking", p["booking_ref"],
                  reason="Booking failed validation (inbound flight not found)")
        audit(con, principal.display_name, MODULE, "JOB_CREATED", "rebooking_job", job_id,
              new={"disrupted": disrupted_flight, "target": target_flight, "total": len(valid),
                   "vulnerable": len(vul), "invalid": len(invalid), "batch_size": size,
                   "vulnerable_policy": vulnerable_codes})
    return job_id


def _external_conflict(target_flight, seat_no, actor):
    """SIMULATED external system reserving a seat the batch planned to use (failure injection)."""
    with tx() as con:
        cur = con.execute("UPDATE seat_inventory SET status='RESERVED', booking_ref='EXTERNAL-SYSTEM', "
                          "version=version+1 WHERE flight_no=? AND seat_no=? AND status='AVAILABLE'",
                          (target_flight, seat_no))
        if cur.rowcount:
            audit(con, actor, "SIMULATOR", "SIMULATED_SEAT_CONFLICT", "seat", f"{target_flight}/{seat_no}",
                  reason="Injected: another channel sold this seat while the batch was being processed")


def process_batch(principal, batch_id, inject=None):
    """Run one batch in its own transaction, with retries on fresh availability, then escalation."""
    require_ops(principal)
    actor = principal.display_name
    b = query_one("SELECT b.*, j.target_flight FROM rebooking_batches b JOIN rebooking_jobs j USING(job_id) "
                  "WHERE batch_id=?", (batch_id,))
    if b is None:
        raise OpsError("NO_BATCH", "Batch not found.")
    if b["status"] == "COMMITTED":
        return b  # idempotent
    max_retries = int(policy("rebooking.max_retries", "2"))
    inject = inject or {}
    conflict_here = inject.get("seat_conflict_batch") == b["seq"] and b["kind"] == "GENERAL"
    persistent = bool(inject.get("persistent"))
    items = query("SELECT * FROM rebooking_batch_items WHERE batch_id=? ORDER BY seq", (batch_id,))
    target = b["target_flight"]
    attempt = b["attempts"]
    while True:
        attempt += 1
        with tx() as con:
            avail = con.execute("SELECT COUNT(*) n FROM seat_inventory WHERE flight_no=? AND status='AVAILABLE'",
                                (target,)).fetchone()["n"]
            _set_batch(con, batch_id, "PROCESSING" if attempt == 1 else "RETRYING", actor, attempts=attempt,
                       started_at=utcnow(), seats_available_at_start=avail)
            if attempt > 1:
                _set_batch(con, batch_id, "PROCESSING", actor)
        # plan with FRESH availability (outside the write transaction)
        free = [r["seat_no"] for r in query(
            "SELECT seat_no FROM seat_inventory WHERE flight_no=? AND status='AVAILABLE' ORDER BY "
            "CAST(substr(seat_no,1,length(seat_no)-1) AS INT), seat_no", (target,))]
        plans, problem = {}, None
        for i, it in enumerate(items):
            if i >= len(free):
                problem = "Not enough seats available on the target flight"
                break
            fp = baggage.calculate_baggage_feasibility(it["booking_ref"], target)
            if fp["decision"] in ("NO_VIABLE_PLAN", "UNKNOWN") or not fp["passenger_feasible"]:
                problem = f"{it['booking_ref']}: no valid baggage plan / passenger cannot make the flight"
                break
            plans[it["booking_ref"]] = (free[i], fp)
        if not problem and conflict_here and (attempt == 1 or persistent):
            _external_conflict(target, free[min(2, len(items) - 1)], actor)
        txn_id = new_id("TXN")
        try:
            if problem:
                raise OpsError("PLAN_FAILED", problem)
            with tx() as con:
                for it in items:
                    seat, fp = plans[it["booking_ref"]]
                    if con.execute("SELECT 1 FROM seat_reservations WHERE booking_ref=? AND flight_no=? AND "
                                   "status='ACTIVE'", (it["booking_ref"], target)).fetchone():
                        raise OpsError("DUPLICATE_BOOKING", f"{it['booking_ref']} already rebooked on {target}")
                    baggage.reserve_seat_cas(con, target, seat, it["booking_ref"], txn_id)   # CAS: conflict → raise
                    old = con.execute("SELECT outbound FROM passengers WHERE booking_ref=?",
                                      (it["booking_ref"],)).fetchone()["outbound"]
                    con.execute("UPDATE passengers SET outbound=? WHERE booking_ref=?", (target, it["booking_ref"]))
                    bag = baggage.apply_bag_plan(con, it["booking_ref"], fp, txn_id)
                    con.execute("UPDATE rebooking_batch_items SET status='COMMITTED', seat_no=?, bag_plan=? "
                                "WHERE batch_id=? AND booking_ref=?", (seat, json.dumps(bag), batch_id, it["booking_ref"]))
                    con.execute("INSERT INTO passenger_rebooking_history(booking_ref,from_flight,to_flight,seat_no,"
                                "txn_id,created_at) VALUES(?,?,?,?,?,?)", (it["booking_ref"], old, target, seat, txn_id,
                                                                           utcnow()))
                    con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) "
                                "VALUES(?,?,'REBOOKED',?,?)", (it["booking_ref"], None,
                                                               f"You have been rebooked on {target}, seat {seat}."
                                                               + (" Your bag is booked on the same flight."
                                                                  if bag and bag["kind"] == "WITH_PASSENGER" else ""),
                                                               utcnow()))
                con.execute("INSERT INTO rebooking_transactions VALUES(?,?,?,?,'COMMITTED',?,?,?)",
                            (txn_id, b["job_id"], batch_id, b["kind"], json.dumps({"passengers": len(items)}),
                             utcnow(), utcnow()))
                _set_batch(con, batch_id, "COMMITTED", actor, finished_at=utcnow(), last_error=None)
                audit(con, actor, MODULE, "TRANSACTION_COMMITTED", "rebooking_batch", batch_id, txn_id=txn_id,
                      result="COMMITTED", new={"passengers": len(items), "kind": b["kind"]})
                outbox(con, "rebooking.batch_committed", {"job_id": b["job_id"], "batch_id": batch_id, "txn_id": txn_id})
            return query_one("SELECT * FROM rebooking_batches WHERE batch_id=?", (batch_id,))
        except OpsError as e:
            # the batch transaction above has rolled back completely; record that in a separate transaction
            with tx() as con:
                con.execute("INSERT INTO rebooking_transactions VALUES(?,?,?,?,'ROLLED_BACK',?,?,?)",
                            (txn_id, b["job_id"], batch_id, b["kind"], str(e), utcnow(), utcnow()))
                _set_batch(con, batch_id, "FAILED", actor, last_error=str(e))
                _set_batch(con, batch_id, "ROLLED_BACK", actor)
                audit(con, actor, MODULE, "TRANSACTION_ROLLED_BACK", "rebooking_batch", batch_id, txn_id=txn_id,
                      reason=str(e), result="ROLLED_BACK")
                if attempt <= max_retries:
                    _set_batch(con, batch_id, "RETRY_PENDING", actor)
                else:
                    _set_batch(con, batch_id, "ESCALATED", actor, escalated_to="OCC controller", finished_at=utcnow())
                    alert(con, MODULE, "HIGH", batch_id, f"Rebooking batch {b['seq']} escalated",
                          f"{len(items)} passengers not rebooked after {attempt} attempts: {e}")
                    outbox(con, "rebooking.batch_escalated", {"job_id": b["job_id"], "batch_id": batch_id,
                                                               "error": str(e)})
            if attempt > max_retries:
                return query_one("SELECT * FROM rebooking_batches WHERE batch_id=?", (batch_id,))


def run_job(principal, job_id, inject=None):
    """Steps 4–12. Priority batch first; then each general batch independently."""
    require_ops(principal)
    job = query_one("SELECT * FROM rebooking_jobs WHERE job_id=?", (job_id,))
    if job is None:
        raise OpsError("NO_JOB", "Job not found.")
    if job["status"] in ("COMPLETED", "COMPLETED_WITH_ESCALATIONS"):
        return report(job_id)
    with tx() as con:
        con.execute("UPDATE rebooking_jobs SET status='PROCESSING' WHERE job_id=?", (job_id,))
        audit(con, principal.display_name, MODULE, "JOB_PROCESSING", "rebooking_job", job_id)
    batches = query("SELECT * FROM rebooking_batches WHERE job_id=? ORDER BY seq", (job_id,))
    for b in batches:                       # seq 0 = PRIORITY, committed before any general batch starts
        with tx() as con:
            if b["status"] == "CREATED":
                _set_batch(con, b["batch_id"], "PENDING", principal.display_name)
        process_batch(principal, b["batch_id"], inject)
    return finish_job(principal, job_id)


def finish_job(principal, job_id):
    rep = report(job_id)
    status = "COMPLETED_WITH_ESCALATIONS" if rep["escalated"] else "COMPLETED"
    with tx() as con:
        con.execute("UPDATE rebooking_jobs SET status=?, completed_at=?, report=? WHERE job_id=?",
                    (status, utcnow(), json.dumps(rep), job_id))
        audit(con, principal.display_name, MODULE, f"JOB_{status}", "rebooking_job", job_id, new=rep)
        outbox(con, "rebooking.job_finished", {"job_id": job_id, "status": status, "report": rep})
    rep["status"] = status
    return rep


def retry_escalated(principal, batch_id):
    """Controller-initiated retry of an escalated batch with fresh availability."""
    require_controller(principal)
    with tx() as con:
        cur = con.execute("UPDATE rebooking_batches SET attempts=0 WHERE batch_id=? AND status='ESCALATED'", (batch_id,))
        if cur.rowcount != 1:
            raise OpsError("NOT_ESCALATED", "Only escalated batches can be retried by the controller.")
        audit(con, principal.display_name, MODULE, "CONTROLLER_RETRY", "rebooking_batch", batch_id)
    b = process_batch(principal, batch_id)
    job_id = query_one("SELECT job_id FROM rebooking_batches WHERE batch_id=?", (batch_id,))["job_id"]
    finish_job(principal, job_id)
    return b


def report(job_id):
    job = query_one("SELECT * FROM rebooking_jobs WHERE job_id=?", (job_id,))
    batches = query("SELECT * FROM rebooking_batches WHERE job_id=? ORDER BY seq", (job_id,))
    committed = [b for b in batches if b["status"] == "COMMITTED"]
    return {"job_id": job_id, "disrupted": job["disrupted_flight"], "target": job["target_flight"],
            "total": job["total"], "vulnerable": job["vulnerable"],
            "batches": [{k: b[k] for k in ("batch_id", "seq", "kind", "status", "passenger_count", "attempts",
                                           "last_error", "seats_available_at_start")} for b in batches],
            "committed_passengers": sum(b["passenger_count"] for b in committed),
            "escalated": [b["batch_id"] for b in batches if b["status"] == "ESCALATED"],
            "rolled_back_transactions": query_one(
                "SELECT COUNT(*) n FROM rebooking_transactions WHERE job_id=? AND status='ROLLED_BACK'",
                (job_id,))["n"]}


def jobs():
    return query("SELECT * FROM rebooking_jobs ORDER BY created_at DESC")


def timeline(job_id):
    ids = [b["batch_id"] for b in query("SELECT batch_id FROM rebooking_batches WHERE job_id=?", (job_id,))] + [job_id]
    q = ",".join("?" * len(ids))
    return query(f"SELECT * FROM audit_events WHERE entity_id IN ({q}) ORDER BY event_id", ids)
