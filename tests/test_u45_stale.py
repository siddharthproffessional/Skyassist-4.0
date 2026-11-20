"""U-4.5 — stale approval protection."""
import pytest

from db import query, query_one, tx
from services import coordinator_service as cs
from services.ops import gate_approvals as ga
from services.ops.foundation import OpsError


def approved(ops, flight="EK-812", gate="B7"):
    a = ga.stage_gate_move(ops, flight, gate)
    ga.approve(ops, a["approval_id"], a["snapshot_hash"])
    return a


def test_b7_given_to_another_flight_makes_approval_stale(ops):
    a = approved(ops)
    ga.assign_gate_direct(ops, "SA-880", "B7")
    r = ga.execute(ops, a["approval_id"])
    assert r["status"] == "STALE" and "GATE:B07" in r["reason"]
    assert query_one("SELECT gate FROM flights WHERE flight_no='EK-812'")["gate"] == "C03"
    assert ga.get(a["approval_id"])["status"] == "STALE"
    assert not query_one("SELECT 1 x FROM operational_actions WHERE approval_id=?", (a["approval_id"],))


def test_stale_approval_restages_a_fresh_proposal_needing_new_decision(ops):
    a = approved(ops)
    ga.assign_gate_direct(ops, "SA-880", "B7")
    r = ga.execute(ops, a["approval_id"])
    n = ga.get(r["new_approval_id"])
    assert n["status"] == "PENDING" and n["parent_id"] == a["approval_id"] and n["payload_dict"]["gate"] != "B07"
    assert ga.execute(ops, n["approval_id"])["code"] == "NOT_APPROVED_PENDING"


def test_unchanged_state_executes_and_bumps_versions(ops):
    a = approved(ops)
    assert ga.execute(ops, a["approval_id"])["status"] == "EXECUTED"
    assert query_one("SELECT version v FROM resource_versions WHERE resource_id='GATE:B07'")["v"] == 2


def test_double_execution_refused(ops):
    a = approved(ops)
    ga.execute(ops, a["approval_id"])
    assert ga.execute(ops, a["approval_id"])["code"] == "ALREADY_EXECUTED"
    assert query_one("SELECT COUNT(*) n FROM operational_actions WHERE approval_id=?", (a["approval_id"],))["n"] == 1


def test_target_substitution_refused(ops):
    a = approved(ops)
    assert ga.execute(ops, a["approval_id"], gate="B9")["code"] == "TARGET_MISMATCH"
    assert ga.execute(ops, a["approval_id"], flight_no="SA-880")["code"] == "TARGET_MISMATCH"


def test_expired_approval_refused(ops):
    a = approved(ops)
    with tx() as con:
        con.execute("UPDATE approval_requests SET expires_at='2000-01-01T00:00:00+00:00' WHERE approval_id=?",
                    (a["approval_id"],))
    assert ga.execute(ops, a["approval_id"])["code"] == "EXPIRED"


def test_approval_requires_the_reviewed_snapshot_hash(ops):
    a = ga.stage_gate_move(ops, "EK-812", "B7")
    with pytest.raises(OpsError) as e:
        ga.approve(ops, a["approval_id"], "0" * 64)
    assert e.value.code == "SNAPSHOT_MISMATCH"


def test_v2_coordinator_gate_change_also_stales_approvals(ops):
    a = approved(ops)
    cs.simulate_gate_change(ops, "SA-880", "B07")
    assert ga.execute(ops, a["approval_id"])["status"] == "STALE"


def test_workflow_e_revalidation_marks_pending_approvals_stale(ops, svc):
    a = ga.stage_gate_move(ops, "EK-812", "B7")
    ga.assign_gate_direct(ops, "SA-880", "B7")
    out = ga.revalidate_affected(svc, ["GATE:B07"])
    assert out and out[0]["approval_id"] == a["approval_id"] and ga.get(a["approval_id"])["status"] == "STALE"


def test_service_identity_cannot_approve_or_execute(ops, svc):
    a = ga.stage_gate_move(svc, "EK-812", "B7")
    with pytest.raises(Exception):
        ga.approve(svc, a["approval_id"], a["snapshot_hash"])
    with pytest.raises(Exception):
        ga.execute(svc, a["approval_id"])


def test_cannot_stage_move_to_occupied_gate(ops):
    ga.assign_gate_direct(ops, "SA-880", "B7")
    with pytest.raises(OpsError) as e:
        ga.stage_gate_move(ops, "EK-812", "B7")
    assert e.value.code == "GATE_OCCUPIED"


def test_rejected_approval_cannot_execute(ops):
    a = ga.stage_gate_move(ops, "EK-812", "B7")
    ga.reject(ops, a["approval_id"], "no")
    assert ga.execute(ops, a["approval_id"])["status"] == "REFUSED"
