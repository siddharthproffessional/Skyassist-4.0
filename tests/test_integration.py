"""Migrations, provenance and UI smoke tests (Streamlit AppTest)."""
import json
import os

import pytest

import build_db
import db
from database.migrations import migrate, schema_report


def test_migrations_idempotent_and_preserve_v1_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "v1.sqlite"))
    con = db.connect()
    build_db.create_base_schema(con)      # a v1 database: original tables only
    build_db.seed_base(con)
    con.execute("INSERT INTO dispatch_requests(id,conv_id,booking_ref,actions,reason,context,status) "
                "VALUES('REQ-OLD','c','PNR1A2','[\"MOBILITY_CART\"]','X','{}','APPROVED')")
    con.commit()
    con.close()
    migrate()
    migrate()                              # second run must be a no-op
    rep = schema_report()
    assert {"terminal_nodes", "terminal_edges", "gate_locations", "navigation_routes", "route_progress", "users",
            "request_events", "notification_events", "audit_log", "staff", "mobility_resources"} <= set(rep)
    assert "dispatch_status" in rep["dispatch_requests"]
    old = db.query_one("SELECT * FROM dispatch_requests WHERE id='REQ-OLD'")
    assert old["status"] == "APPROVED" and old["dispatch_status"] == "NONE" and old["created_at_utc"]
    assert db.query_one("SELECT COUNT(*) n FROM terminal_nodes")["n"] == db.query_one(
        "SELECT COUNT(*) n FROM terminal_nodes")["n"] > 60
    assert db.query_one("SELECT COUNT(*) n FROM users")["n"] == 12


def test_timestamps_are_utc(fresh_db):
    from services.request_store import create_request
    rid, _ = create_request("c", None, ["MOBILITY_CART"], "X", {})
    assert db.query_one("SELECT created_at_utc FROM dispatch_requests WHERE id=?", (rid,))["created_at_utc"].endswith("+00:00")


def test_future_integrations_are_not_faked():
    from services.integrations import LiveFlightProvider, NotConfigured, SkyOpsTwinTopologyProvider
    from services.location_provider import BeaconLocationProvider, QRCheckpointLocationProvider
    for call in (lambda: LiveFlightProvider().get_flight("SA-218"), lambda: SkyOpsTwinTopologyProvider().edges(),
                 lambda: BeaconLocationProvider().current("x", "C12"), lambda: QRCheckpointLocationProvider().current("x", "C12")):
        with pytest.raises(NotConfigured):
            call()


# ---------------------------------------------------------------- UI smoke tests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app(view, principal=None, role=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "views", view), default_timeout=30)
    if principal:
        at.session_state["principals"] = {role: principal}
    return at.run()


def test_ui_passenger_portal_renders_for_signed_in_passenger(pax):
    at = _app("passenger.py", pax, "PASSENGER")
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "B14" in html and "AT RISK" in html and "Waiting for airport coordinator approval" in html


def test_ui_passenger_portal_requires_sign_in(fresh_db):
    at = _app("passenger.py")
    assert not at.exception and any(b.label == "Sign in" for b in at.button) or len(at.text_input) == 2


def test_ui_coordinator_portal_rejects_passenger_session(pax):
    at = _app("coordinator.py", pax, "PASSENGER")     # a passenger principal is not a coordinator principal
    assert not at.exception
    assert not any("APPROVE" in b.label for b in at.button)
    assert len(at.text_input) == 2                      # shows the coordinator sign-in form instead


def test_ui_coordinator_portal_renders_queue(coord):
    from services import passenger_service
    from services.auth_service import authenticate
    passenger_service.get_journey(authenticate("PNR1A2", "demo123", "PASSENGER"), "PNR1A2")
    at = _app("coordinator.py", coord, "COORDINATOR")
    assert not at.exception
    assert any(b.label.startswith("Open REQ-") for b in at.button)
