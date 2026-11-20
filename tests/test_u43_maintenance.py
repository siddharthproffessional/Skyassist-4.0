"""U-4.3 — maintenance sign-off validation: an 'OK' is a claim, not evidence."""
from db import query, query_one
from services.ops import maintenance as mx

BAD = ("E-999", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK", "2026-11-20T07:00:00+00:00", "WO-7781")
GOOD = ("E-501", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK", "2026-11-20T09:15:00+00:00", "WO-7781")


def failed(r):
    return {c["check"].split(" ")[0] for c in r["checks"] if not c["passed"]}


def test_unlicensed_pre_defect_signoff_is_invalid_and_departure_blocked(ops):
    r = mx.submit_signoff(ops, *BAD)
    assert r["status"] == "INVALID" and r["departure_blocked"]
    assert {"1", "2", "3", "8"} <= failed(r)
    assert mx.departure_status("SA-710")["blocked"]
    assert query_one("SELECT 1 x FROM operational_alerts WHERE module='MAINTENANCE' AND severity='CRITICAL'")


def test_invalid_record_is_preserved_unchanged(ops):
    r = mx.submit_signoff(ops, *BAD)
    s = query_one("SELECT * FROM maintenance_signoffs WHERE signoff_id=?", (r["signoff_id"],))
    assert (s["engineer_id"], s["result"], s["signed_at_utc"]) == ("E-999", "OK", "2026-11-20T07:00:00+00:00")
    assert len(mx.validation_events(r["signoff_id"])) == len(r["checks"])


def test_valid_replacement_clears_defect_but_not_final_release(ops):
    mx.submit_signoff(ops, *BAD)
    r = mx.submit_signoff(ops, *GOOD)
    assert r["status"] == "VALID" and not r["departure_blocked"]
    assert query_one("SELECT status FROM aircraft_defects WHERE defect_id='DEF-HYD-1'")["status"] == "CLEARED"
    assert query_one("SELECT status FROM aircraft WHERE reg='A6-SKB'")["status"] == "AWAITING_FINAL_RELEASE"
    assert len(mx.signoffs("DEF-HYD-1")) == 2   # invalid record kept beside the valid one


def test_expired_licence_rejected(ops):
    assert "3" in failed(mx.submit_signoff(ops, "E-502", *GOOD[1:]))


def test_wrong_aircraft_type_rejected(ops):
    assert "4" in failed(mx.submit_signoff(ops, "E-503", *GOOD[1:]))


def test_wrong_scope_rejected(ops):
    assert "5" in failed(mx.submit_signoff(ops, "E-504", *GOOD[1:]))


def test_registration_mismatch_rejected(ops):
    args = list(GOOD); args[2] = "A6-XXX"
    assert "6" in failed(mx.submit_signoff(ops, *args))


def test_evidence_from_another_defect_rejected(ops):
    args = list(GOOD); args[6] = "WO-9001"
    assert "10" in failed(mx.submit_signoff(ops, *args))


def test_future_timestamp_rejected(ops):
    args = list(GOOD); args[5] = "2099-01-01T00:00:00+00:00"
    assert "8" in failed(mx.submit_signoff(ops, *args))


def test_garbage_timestamp_does_not_crash_and_is_invalid(ops):
    args = list(GOOD); args[5] = "yesterday-ish"
    assert mx.submit_signoff(ops, *args)["status"] == "INVALID"


def test_evidence_reuse_after_valid_signoff_rejected(ops):
    mx.submit_signoff(ops, *GOOD)
    args = list(GOOD); args[5] = "2026-11-20T09:20:00+00:00"
    assert "9" in failed(mx.submit_signoff(ops, *args))


def test_non_clearance_result_rejected(ops):
    args = list(GOOD); args[4] = "DEFERRED"
    assert mx.submit_signoff(ops, *args)["status"] == "INVALID"


def test_signoff_cannot_be_validated_twice(ops):
    import pytest
    from services.ops.foundation import OpsError
    r = mx.submit_signoff(ops, *BAD)
    with pytest.raises(OpsError):
        mx.validate_maintenance_signoff(ops, r["signoff_id"])


def test_demo_reset_does_not_let_old_signoffs_count_as_reuse(ops):
    from services.ops import seed
    mx.submit_signoff(ops, *GOOD)
    seed.reset_ops_demo("tester")
    assert mx.submit_signoff(ops, *GOOD)["status"] == "VALID"
