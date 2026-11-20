"""Role-based access, enforced in the backend (acceptance 9, 24, 34)."""
import pytest

from services import coordinator_service as cs, passenger_service
from services.auth_service import AuthError, PermissionDenied, authenticate


def test_09_passenger_cannot_use_coordinator_functions(pax):
    rid = passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"]
    for call in (lambda: cs.list_requests(pax), lambda: cs.kpis(pax), lambda: cs.request_detail(pax, rid),
                 lambda: cs.decide(pax, rid, True), lambda: cs.assign(pax, rid, "ST-01"),
                 lambda: cs.simulate_gate_change(pax, "SA-218", "B01"), lambda: cs.audit_log(pax)):
        with pytest.raises(PermissionDenied):
            call()


def test_24_unauthenticated_cannot_decide(pax):
    rid = passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"]
    with pytest.raises(PermissionDenied):
        cs.decide(None, rid, True)
    from services import request_store
    assert request_store.get(rid)["status"] == "PENDING"


def test_passenger_cannot_read_another_booking(pax):
    with pytest.raises(PermissionDenied):
        passenger_service.get_journey(pax, "PNR3C4")


def test_34_two_passengers_see_only_their_own_data(fresh_db):
    a = authenticate("PNR1A2", "demo123", "PASSENGER")
    b = authenticate("PNR9J1", "demo123", "PASSENGER")
    ja, jb = passenger_service.get_journey(a, "PNR1A2"), passenger_service.get_journey(b, "PNR9J1")
    assert ja["outbound"]["gate"] == "B14" and jb["outbound"]["gate"] == "C04"
    assert ja["assistance"]["request"] and jb["assistance"]["request"] is None


def test_wrong_portal_and_bad_password_refused(fresh_db):
    with pytest.raises(AuthError):
        authenticate("PNR1A2", "demo123", "COORDINATOR")
    with pytest.raises(AuthError):
        authenticate("sarah", "coord123", "PASSENGER")
    with pytest.raises(AuthError):
        authenticate("sarah", "wrong", "COORDINATOR")


def test_passwords_are_hashed(fresh_db):
    from db import query
    rows = query("SELECT password_hash, salt FROM users")
    assert rows and all(len(r["password_hash"]) == 64 and r["password_hash"] not in ("demo123", "coord123") for r in rows)
