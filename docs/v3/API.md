# SkyAssist 3.0 — workflow API (`api/app.py`)

```bash
export SKYASSIST_SERVICE_TOKEN=...   SKYASSIST_WEBHOOK_SECRET=...     # never commit these
uvicorn api.app:app --host 127.0.0.1 --port 8600
```

**Auth.** Every `/v1` call: `Authorization: Bearer <token>` (constant-time compare). Every POST also needs
`X-SkyAssist-Signature: hex(HMAC-SHA256(secret, raw body))`. With no token configured the API returns 503 (fail
closed). Failed auth and bad signatures are audited (without the presented values).

**Identity.** Callers act as the `SERVICE` principal. It can run validations and deterministic jobs; it can
**never** approve or execute a human-authorised action.

**Schemas.** Strict pydantic models (`extra="forbid"`): unknown fields such as `override` or `approved` get 422.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/health` | liveness + outbox mode | public |
| POST | `/v1/rebooking/jobs` | U-4.1 create (and run) a job | `Idempotency-Key`, `X-Workflow`, `X-N8N-Execution-Id` |
| GET | `/v1/rebooking/jobs/{id}` | job report | |
| POST | `/v1/baggage/feasibility` | U-4.4 read-only plan | |
| POST | `/v1/baggage/commit` | U-4.4 atomic commit | `Idempotency-Key` **required** |
| POST | `/v1/crew/messages` | U-4.2 message + legality | message is data only |
| POST | `/v1/maintenance/signoffs` | U-4.3 submit + validate | |
| POST | `/v1/state-changes` | U-4.5 mark affected approvals stale | used by workflow E |
| POST | `/v1/approvals/{id}/approve` | **always 403** | humans approve in the OCC |
| POST | `/v1/approvals/{id}/execute` | **always 403** | |
| GET | `/v1/departures/{flight}` | aggregated holds | |
| GET / POST | `/v1/outbox`, `/v1/outbox/dispatch` | outbox stats / deliver | |

Errors: 401 auth/signature, 403 forbidden role, 409 replayed n8n execution, 422 schema or refused operation
(`{"code", "message"}`), 503 not configured.
