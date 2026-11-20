"""SkyAssist 3.0 foundation: additive migration, append-only audit, immutability, idempotency, safe reset."""
import sqlite3

import pytest

import build_db
from db import connect, query, query_one, tx
from services.auth_service import PermissionDenied, authenticate
from services.ops import foundation as F
from services.ops import seed


def test_schema_v3_is_additive_and_idempotent(ops):
    before = {r["name"] for r in query("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("users", "passengers", "flights", "dispatch_requests", "request_events", "notification_events", "audit_log"):
        assert t in before, f"v2 table {t} must survive"
    pax_before = query_one("SELECT COUNT(*) n FROM passengers")["n"]
    build_db.ensure_database()          # re-running migrations must not overwrite or duplicate anything
    seed.ensure_seeded()
    assert query_one("SELECT COUNT(*) n FROM passengers")["n"] == pax_before
    assert query_one("SELECT MAX(version) v FROM schema_migrations")["v"] == 3


def test_audit_events_are_append_only(ops):
    F.audit_now("tester", "TEST", "PROBE")
    con = connect()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE audit_events SET actor='x'")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM audit_events")
    con.close()


def test_duty_rule_profiles_cannot_be_updated(ops):
    con = connect()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE duty_rule_profiles SET max_duty_min=9999")
    con.close()


def test_idempotency_key_cannot_be_reused_for_another_operation(ops):
    with tx() as con:
        F.idem_store(con, "k-1", "OP_A", {"a": 1}, {"ok": True})
    with tx() as con:
        assert F.idem_lookup(con, "k-1", "OP_A") == {"ok": True}
        with pytest.raises(F.OpsError) as e:
            F.idem_lookup(con, "k-1", "OP_B")
    assert e.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_version_compare_and_bump(ops):
    with tx() as con:
        assert F.version_of(con, "GATE:Z99") == 1
        F.bump(con, "GATE:Z99")
        assert F.version_of(con, "GATE:Z99") == 2


def test_passenger_cannot_use_ops_services(ops):
    p = authenticate("PNR1A2", "demo123", "PASSENGER")
    with pytest.raises(PermissionDenied):
        F.require_ops(p)


def test_service_identity_can_never_act_as_controller(ops, svc):
    F.require_ops(svc)
    with pytest.raises(PermissionDenied):
        F.require_controller(svc)


def test_demo_reset_keeps_audit_signoffs_and_v2_data(ops):
    from services.ops import maintenance
    maintenance.submit_signoff(ops, "E-999", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK",
                               "2026-11-20T07:00:00+00:00", "WO-7781")
    audit_n = query_one("SELECT COUNT(*) n FROM audit_events")["n"]
    users_n = query_one("SELECT COUNT(*) n FROM users")["n"]
    v2_pax = query_one("SELECT COUNT(*) n FROM passengers WHERE booking_ref NOT LIKE 'OPS%' AND booking_ref!='PNRBAG'")["n"]
    seed.reset_ops_demo("tester")
    assert query_one("SELECT COUNT(*) n FROM audit_events")["n"] > audit_n          # reset itself is audited
    assert query_one("SELECT COUNT(*) n FROM maintenance_signoffs")["n"] == 1       # immutable record kept
    assert query_one("SELECT COUNT(*) n FROM users")["n"] == users_n
    assert query_one("SELECT COUNT(*) n FROM passengers WHERE booking_ref NOT LIKE 'OPS%' AND booking_ref!='PNRBAG'")["n"] == v2_pax
    assert query_one("SELECT 1 x FROM audit_events WHERE event_type='DEMO_RESET'")


def test_maintenance_signoff_core_fields_are_immutable(ops):
    from services.ops import maintenance
    r = maintenance.submit_signoff(ops, "E-501", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK",
                                   "2026-11-20T09:15:00+00:00", "WO-7781")
    con = connect()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE maintenance_signoffs SET engineer_id='E-000' WHERE signoff_id=?", (r["signoff_id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE maintenance_signoffs SET validation_status='INVALID' WHERE signoff_id=?", (r["signoff_id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM maintenance_signoffs")
    con.close()
