"""U-4.1 — vulnerable passengers first, own transaction; batches of 10; batch-3 failure isolated."""
import json

import pytest

from db import query, query_one
from services.ops import rebooking
from services.ops.foundation import OpsError


def _run(ops, persistent=True, conflict=3):
    job = rebooking.create_job(ops, "SA-560", "SA-562")
    return job, rebooking.run_job(ops, job, {"seat_conflict_batch": conflict, "persistent": persistent})


def test_vulnerable_passengers_get_their_own_priority_transaction(ops):
    job, rep = _run(ops, conflict=None)
    b0 = rep["batches"][0]
    assert b0["kind"] == "PRIORITY" and b0["passenger_count"] == 6 and b0["status"] == "COMMITTED"
    refs = [r["booking_ref"] for r in query("SELECT booking_ref FROM rebooking_batch_items WHERE batch_id=?",
                                            (b0["batch_id"],))]
    for r in refs:
        needs = json.loads(query_one("SELECT needs FROM passengers WHERE booking_ref=?", (r,))["needs"])
        assert set(needs) & {"WCHR", "UMNR", "ELDERLY"}
    txns = query("SELECT * FROM rebooking_transactions WHERE batch_id=?", (b0["batch_id"],))
    assert len(txns) == 1 and txns[0]["kind"] == "PRIORITY"


def test_priority_commits_before_any_general_batch_starts(ops):
    job, _ = _run(ops, conflict=None)
    ev = query("SELECT entity_id, event_type, event_id FROM audit_events WHERE module='REBOOKING' AND "
               "event_type IN ('TRANSACTION_COMMITTED','BATCH_PROCESSING') ORDER BY event_id")
    p_commit = next(e["event_id"] for e in ev if e["entity_id"].endswith("-P0") and e["event_type"] == "TRANSACTION_COMMITTED")
    first_general = min(e["event_id"] for e in ev if "-B" in e["entity_id"] and e["event_type"] == "BATCH_PROCESSING")
    assert p_commit < first_general


def test_general_passengers_split_into_batches_of_ten(ops):
    _, rep = _run(ops, conflict=None)
    gen = [b for b in rep["batches"] if b["kind"] == "GENERAL"]
    assert [b["passenger_count"] for b in gen] == [10, 10, 10, 4]
    assert rep["committed_passengers"] == 40 and rep["status"] == "COMPLETED"


def test_batch_three_conflict_rolls_back_only_batch_three(ops):
    _, rep = _run(ops, persistent=True)
    st = {b["seq"]: b["status"] for b in rep["batches"]}
    assert st == {0: "COMMITTED", 1: "COMMITTED", 2: "COMMITTED", 3: "ESCALATED", 4: "COMMITTED"}
    b3 = next(b for b in rep["batches"] if b["seq"] == 3)
    assert query_one("SELECT COUNT(*) n FROM rebooking_batch_items WHERE batch_id=? AND status='COMMITTED'",
                     (b3["batch_id"],))["n"] == 0
    assert query_one("SELECT COUNT(*) n FROM seat_reservations sr JOIN rebooking_batch_items i ON "
                     "i.booking_ref=sr.booking_ref WHERE i.batch_id=?", (b3["batch_id"],))["n"] == 0
    for r in query("SELECT booking_ref FROM rebooking_batch_items WHERE batch_id=?", (b3["batch_id"],)):
        assert query_one("SELECT outbound FROM passengers WHERE booking_ref=?", (r["booking_ref"],))["outbound"] == "SA-560"
    assert rep["committed_passengers"] == 30


def test_transient_conflict_is_retried_with_fresh_availability(ops):
    _, rep = _run(ops, persistent=False)
    b3 = next(b for b in rep["batches"] if b["seq"] == 3)
    assert b3["status"] == "COMMITTED" and b3["attempts"] == 2
    assert rep["committed_passengers"] == 40
    assert query_one("SELECT COUNT(*) n FROM rebooking_transactions WHERE batch_id=? AND status='ROLLED_BACK'",
                     (b3["batch_id"],))["n"] == 1


def test_exhausted_retries_escalate_to_controller_with_alert(ops):
    _, rep = _run(ops, persistent=True)
    b3 = next(b for b in rep["batches"] if b["seq"] == 3)
    assert b3["attempts"] == 3 and rep["escalated"] == [b3["batch_id"]]
    assert query_one("SELECT 1 x FROM operational_alerts WHERE entity_id=? AND module='REBOOKING'", (b3["batch_id"],))
    assert rep["status"] == "COMPLETED_WITH_ESCALATIONS"


def test_no_passenger_is_double_booked_and_no_seat_is_double_sold(ops):
    _run(ops, persistent=False)
    assert query_one("SELECT COUNT(*) n FROM (SELECT booking_ref FROM seat_reservations WHERE status='ACTIVE' "
                     "GROUP BY booking_ref, flight_no HAVING COUNT(*)>1)")["n"] == 0
    assert query_one("SELECT COUNT(*) n FROM (SELECT seat_no FROM seat_reservations WHERE status='ACTIVE' "
                     "GROUP BY flight_no, seat_no HAVING COUNT(*)>1)")["n"] == 0


def test_job_creation_is_idempotent(ops):
    a = rebooking.create_job(ops, "SA-560", "SA-562", "dup-key")
    b = rebooking.create_job(ops, "SA-560", "SA-562", "dup-key")
    assert a == b and query_one("SELECT COUNT(*) n FROM rebooking_jobs")["n"] == 1


def test_rerunning_a_completed_job_changes_nothing(ops):
    job, rep = _run(ops, conflict=None)
    n = query_one("SELECT COUNT(*) n FROM seat_reservations")["n"]
    rebooking.run_job(ops, job)
    assert query_one("SELECT COUNT(*) n FROM seat_reservations")["n"] == n


def test_controller_retry_of_escalated_batch(ops):
    _, rep = _run(ops, persistent=True)
    b3 = rep["escalated"][0]
    out = rebooking.retry_escalated(ops, b3)
    assert out["status"] == "COMMITTED"


def test_service_identity_cannot_retry_escalations(ops, svc):
    _, rep = _run(ops, persistent=True)
    with pytest.raises(Exception):
        rebooking.retry_escalated(svc, rep["escalated"][0])


def test_rebooked_passenger_sees_new_flight_in_v2_portal(ops):
    from services.passenger_service import get_journey
    from services.auth_service import authenticate
    _run(ops, conflict=None)
    p = authenticate("OPS001", "demo123", "PASSENGER")
    j = get_journey(p, "OPS001")
    assert j["outbound"]["flight_no"] == "SA-562"


def test_bad_target_flight_refused(ops):
    with pytest.raises(OpsError):
        rebooking.create_job(ops, "SA-560", "SA-560")
