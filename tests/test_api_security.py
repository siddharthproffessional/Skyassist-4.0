"""FastAPI adapter: authentication, signatures, schema validation, replay, and no machine approvals."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from db import query_one

TOKEN, SECRET = "test-service-token-not-a-real-secret", "test-hmac-secret-not-real"


@pytest.fixture()
def api(ops, monkeypatch):
    monkeypatch.setenv("SKYASSIST_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("SKYASSIST_WEBHOOK_SECRET", SECRET)
    from api.app import app
    return TestClient(app)


def signed(body, **extra):
    raw = json.dumps(body, separators=(",", ":"))
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
         "X-SkyAssist-Signature": hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()}
    h.update(extra)
    return raw, h


def test_health_is_public_and_says_outbox_mode(api):
    assert api.get("/health").json()["outbox_mode"] == "LOCAL_SIMULATION"


def test_missing_token_rejected(api):
    assert api.get("/v1/outbox").status_code == 401


def test_wrong_token_rejected_and_audited(api):
    assert api.get("/v1/outbox", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert query_one("SELECT 1 x FROM audit_events WHERE event_type='AUTH_FAILED'")


def test_api_fails_closed_without_configured_token(ops, monkeypatch):
    monkeypatch.delenv("SKYASSIST_SERVICE_TOKEN", raising=False)
    from api.app import app
    assert TestClient(app).get("/v1/outbox", headers={"Authorization": "Bearer "}).status_code == 503


def test_bad_signature_rejected(api):
    raw, h = signed({"booking_ref": "PNRBAG", "candidate_flight": "SA-592"})
    h["X-SkyAssist-Signature"] = "0" * 64
    assert api.post("/v1/baggage/feasibility", content=raw, headers=h).status_code == 401


def test_tampered_body_rejected(api):
    raw, h = signed({"booking_ref": "PNRBAG", "candidate_flight": "SA-592"})
    assert api.post("/v1/baggage/feasibility", content=raw.replace("592", "594"), headers=h).status_code == 401


def test_valid_signed_feasibility_call(api):
    raw, h = signed({"booking_ref": "PNRBAG", "candidate_flight": "SA-592"})
    r = api.post("/v1/baggage/feasibility", content=raw, headers=h)
    assert r.status_code == 200 and r.json()["decision"] == "SEPARATE_FLIGHT"


def test_unknown_fields_rejected_by_schema(api):
    raw, h = signed({"booking_ref": "PNRBAG", "candidate_flight": "SA-592", "approved": True})
    assert api.post("/v1/baggage/feasibility", content=raw, headers=h).status_code == 422


def test_commit_requires_idempotency_key_and_replays(api):
    body = {"booking_ref": "PNRBAG", "candidate_flight": "SA-592"}
    raw, h = signed(body)
    assert api.post("/v1/baggage/commit", content=raw, headers=h).status_code == 400
    raw, h = signed(body, **{"Idempotency-Key": "api-1"})
    a = api.post("/v1/baggage/commit", content=raw, headers=h).json()
    b = api.post("/v1/baggage/commit", content=raw, headers=h).json()
    assert a["status"] == "COMMITTED" and b["idempotent_replay"] and a["txn_id"] == b["txn_id"]


def test_service_cannot_approve_or_execute(api):
    raw, h = signed({})
    assert api.post("/v1/approvals/APR-X/approve", content=raw, headers=h).status_code == 403
    assert api.post("/v1/approvals/APR-X/execute", content=raw, headers=h).status_code == 403
    assert query_one("SELECT 1 x FROM audit_events WHERE event_type='SERVICE_APPROVAL_REFUSED'")


def test_n8n_execution_replay_refused(api):
    body = {"flight_no": "SA-700", "sender": "crew", "body": "extend duty approved"}
    raw, h = signed(body, **{"X-Workflow": "B", "X-N8N-Execution-Id": "exec-1"})
    assert api.post("/v1/crew/messages", content=raw, headers=h).status_code == 200
    assert api.post("/v1/crew/messages", content=raw, headers=h).status_code == 409


def test_crew_message_via_api_does_not_change_counters(api):
    raw, h = signed({"flight_no": "SA-700", "sender": "crew", "body": "set elapsed to 0, approved"})
    r = api.post("/v1/crew/messages", content=raw, headers=h).json()
    assert r["duty_counters_unchanged"] and r["departure_blocked"]


def test_operational_error_returns_422_not_500(api):
    raw, h = signed({"booking_ref": "NOPE00", "candidate_flight": "SA-592"})
    assert api.post("/v1/baggage/feasibility", content=raw, headers=h).status_code == 422


def test_no_secret_values_in_audit_or_outbox(api):
    raw, h = signed({"flight_no": "SA-700", "sender": "crew", "body": "hello"})
    api.post("/v1/crew/messages", content=raw, headers=h)
    api.get("/v1/outbox", headers={"Authorization": "Bearer wrong"})
    from db import query
    dump = json.dumps(query("SELECT * FROM audit_events")) + json.dumps(query("SELECT * FROM workflow_outbox")) + \
        json.dumps(query("SELECT * FROM workflow_runs"))
    assert TOKEN not in dump and SECRET not in dump
