"""SkyAssist 3.0 — authenticated FastAPI adapter for n8n workflows.

Run:  SKYASSIST_SERVICE_TOKEN=... SKYASSIST_WEBHOOK_SECRET=... uvicorn api.app:app --port 8600

Security model
* Every /v1 call needs `Authorization: Bearer <SKYASSIST_SERVICE_TOKEN>` (constant-time compare). If the token
  is not configured the API refuses everything (fail closed).
* Mutating calls also need `X-SkyAssist-Signature: hex(HMAC-SHA256(SKYASSIST_WEBHOOK_SECRET, raw body))`.
* The caller is the SERVICE principal: it may trigger validations and deterministic jobs; it can never approve
  or execute a human-authorised action (those routes return 403 by design).
* Idempotency-Key is honoured on job-creating calls; X-N8N-Execution-Id is logged once per workflow (replays 409).
* Request bodies are schema-validated (pydantic, extra fields forbidden). Secrets are never logged.
"""
import hashlib
import hmac
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

import build_db  # noqa: E402
from db import query_one, tx, utcnow  # noqa: E402
from services.auth_service import PermissionDenied, Principal  # noqa: E402
from services.ops import baggage, crew, gate_approvals, maintenance, outbox, rebooking  # noqa: E402
from services.ops import seed  # noqa: E402
from services.ops.foundation import SERVICE, OpsError, audit_now  # noqa: E402

SERVICE_PRINCIPAL = Principal("n8n-service", SERVICE, "n8n workflow service")


@asynccontextmanager
async def lifespan(_app):
    build_db.ensure_database()
    seed.ensure_seeded()
    yield


app = FastAPI(title="SkyAssist 3.0 workflow adapter", version="3.0.0", lifespan=lifespan)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RebookingJobIn(Strict):
    disrupted_flight: str = Field(pattern=r"^[A-Z0-9]{2}-?\d{2,4}$")
    target_flight: str = Field(pattern=r"^[A-Z0-9]{2}-?\d{2,4}$")
    run: bool = True


class BaggageIn(Strict):
    booking_ref: str = Field(min_length=3, max_length=12)
    candidate_flight: str = Field(pattern=r"^[A-Z0-9]{2}-?\d{2,4}$")


class CrewMessageIn(Strict):
    flight_no: str = Field(pattern=r"^[A-Z0-9]{2}-?\d{2,4}$")
    sender: str = Field(max_length=80)
    body: str = Field(max_length=2000)


class SignoffIn(Strict):
    engineer_id: str = Field(max_length=20)
    defect_id: str = Field(max_length=30)
    reg: str = Field(max_length=12)
    task_scope: str = Field(max_length=30)
    result: str = Field(max_length=20)
    signed_at_utc: str = Field(max_length=40)
    evidence_ref: str = Field(max_length=30)


class StateChangeIn(Strict):
    resources: List[str] = Field(min_length=1, max_length=20)
    reason: Optional[str] = Field(default=None, max_length=200)


def _const_eq(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a, b)


async def service_auth(request: Request, authorization: str = Header(default=""),
                       x_skyassist_signature: str = Header(default="")):
    token = os.environ.get("SKYASSIST_SERVICE_TOKEN", "")
    if not token:
        raise HTTPException(503, "Service token not configured — API is closed (fail closed).")
    if not _const_eq(authorization.removeprefix("Bearer ").strip(), token):
        audit_now("anonymous", "API", "AUTH_FAILED", reason=f"{request.method} {request.url.path}", result="REFUSED")
        raise HTTPException(401, "Invalid or missing service token.")
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        secret = os.environ.get("SKYASSIST_WEBHOOK_SECRET", "")
        body = await request.body()
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else ""
        if not _const_eq(x_skyassist_signature, expected):
            audit_now(SERVICE_PRINCIPAL.display_name, "API", "SIGNATURE_INVALID", reason=request.url.path,
                      result="REFUSED")
            raise HTTPException(401, "Invalid webhook signature.")
    return SERVICE_PRINCIPAL


def log_run(workflow: Optional[str], execution_id: Optional[str], status: str, detail: dict):
    if not workflow or not execution_id:
        return
    try:
        with tx() as con:
            con.execute("INSERT INTO workflow_runs(workflow,execution_id,status,detail,created_at) VALUES(?,?,?,?,?)",
                        (workflow, execution_id, status, json.dumps(detail, default=str)[:4000], utcnow()))
    except Exception:
        raise HTTPException(409, f"Execution {execution_id} of {workflow} was already processed (replay refused).")


def _ops(fn):
    try:
        return fn()
    except OpsError as e:
        raise HTTPException(422, {"code": e.code, "message": str(e)})
    except PermissionDenied as e:
        raise HTTPException(403, str(e))


@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0", "outbox_mode": outbox.mode()}


@app.post("/v1/rebooking/jobs")
def create_rebooking_job(body: RebookingJobIn, p=Depends(service_auth), idempotency_key: str = Header(default=""),
                         x_workflow: str = Header(default=None), x_n8n_execution_id: str = Header(default=None)):
    log_run(x_workflow, x_n8n_execution_id, "RECEIVED", body.model_dump())

    def go():
        job = rebooking.create_job(p, body.disrupted_flight, body.target_flight, idempotency_key or None)
        return rebooking.run_job(p, job) if body.run else {"job_id": job}
    return _ops(go)


@app.get("/v1/rebooking/jobs/{job_id}")
def get_job(job_id: str, p=Depends(service_auth)):
    if not query_one("SELECT 1 x FROM rebooking_jobs WHERE job_id=?", (job_id,)):
        raise HTTPException(404, "Unknown job.")
    return rebooking.report(job_id)


@app.post("/v1/baggage/feasibility")
def baggage_feasibility(body: BaggageIn, p=Depends(service_auth)):
    return _ops(lambda: baggage.calculate_baggage_feasibility(body.booking_ref, body.candidate_flight))


@app.post("/v1/baggage/commit")
def baggage_commit(body: BaggageIn, p=Depends(service_auth), idempotency_key: str = Header(default="")):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required for commits.")
    return _ops(lambda: baggage.commit_rebooking_with_baggage(p, body.booking_ref, body.candidate_flight,
                                                              idempotency_key))


@app.post("/v1/crew/messages")
def crew_message(body: CrewMessageIn, p=Depends(service_auth), x_workflow: str = Header(default=None),
                 x_n8n_execution_id: str = Header(default=None)):
    log_run(x_workflow, x_n8n_execution_id, "RECEIVED", {"flight_no": body.flight_no})
    return _ops(lambda: crew.evaluate_flight(p, body.flight_no, body.body, body.sender))


@app.post("/v1/maintenance/signoffs")
def maintenance_signoff(body: SignoffIn, p=Depends(service_auth), x_workflow: str = Header(default=None),
                        x_n8n_execution_id: str = Header(default=None)):
    log_run(x_workflow, x_n8n_execution_id, "RECEIVED", {"defect": body.defect_id})
    return _ops(lambda: maintenance.submit_signoff(p, **body.model_dump(), submitted_by="n8n intake"))


@app.post("/v1/state-changes")
def state_change(body: StateChangeIn, p=Depends(service_auth), x_workflow: str = Header(default=None),
                 x_n8n_execution_id: str = Header(default=None)):
    log_run(x_workflow, x_n8n_execution_id, "RECEIVED", body.model_dump())
    return {"revalidated": _ops(lambda: gate_approvals.revalidate_affected(p, body.resources))}


@app.post("/v1/approvals/{approval_id}/approve")
def approve_via_service(approval_id: str, p=Depends(service_auth)):
    """Deliberately refused: approvals are human decisions in the OCC, never a workflow step."""
    audit_now(p.display_name, "API", "SERVICE_APPROVAL_REFUSED", entity_type="approval", entity_id=approval_id,
              result="REFUSED", reason="Machine identity cannot approve")
    raise HTTPException(403, "The service identity cannot approve or execute operational actions.")


@app.post("/v1/approvals/{approval_id}/execute")
def execute_via_service(approval_id: str, p=Depends(service_auth)):
    return approve_via_service(approval_id, p)


@app.get("/v1/departures/{flight_no}")
def departure(flight_no: str, p=Depends(service_auth)):
    return maintenance.departure_status(flight_no)


@app.get("/v1/outbox")
def outbox_view(p=Depends(service_auth)):
    return {"mode": outbox.mode(), "stats": outbox.stats()}


@app.post("/v1/outbox/dispatch")
def outbox_dispatch(p=Depends(service_auth)):
    return outbox.dispatch()
