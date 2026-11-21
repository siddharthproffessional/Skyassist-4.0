# SkyAssist 4.0 — feature preservation register

Contract: 4.0 is **another interface** to the existing system. Every 2.0, 3.0 and Round 3 capability keeps working,
the Streamlit application stays the operational fallback, and the n8n adapter is unchanged.

## How it was checked

1. Baseline before any 4.0 change (2026-11-21): `docs/v4/baseline/pytest_baseline.txt` (**239 passed**) and
   `docs/v4/baseline/scenarios_baseline.txt` (**10/10**). SHA-256 of every test file:
   `docs/v4/baseline/tests_sha256_before.txt`.
2. After 4.0: every pre-existing test file is **byte-identical** (hash diff shows only the new
   `tests/test_v4_web.py`). Full suite: **264 passed** (`docs/v4/pytest_full_v4.txt`); `run_scenarios.py`: **10/10**
   (`docs/v4/scenarios_v4.txt`).

## Existing files touched by 4.0

| File | Change | Why it cannot break 2.0/3.0 |
|---|---|---|
| `database/migrations.py` | 2 lines: call `migrate_v4` after `migrate_v3` | v4 migration is `CREATE … IF NOT EXISTS` + `INSERT OR IGNORE`; it does not record a new `schema_migrations` version, so the v3 assertion `MAX(version) == 3` still holds |

Everything else is new: `api/web.py`, `api/server.py`, `services/agents/*`, `services/twin/*`,
`services/ops/disruptions.py`, `database/migrations_v4.py`, `frontend/*`, `scripts/bench_v4.py`,
`scripts/qa_browser_v4.py`, `tests/test_v4_web.py`, `docs/v4/*`.

## Register

| # | Capability | 4.0 status | Evidence |
|---|---|---|---|
| 1 | Passenger portal (Streamlit) | Unchanged; new mobile `/passenger` added beside it | v2 tests unchanged + pass |
| 2 | Coordinator portal, Operations overview, OCC (Streamlit) | Unchanged — operational fallback | test_coordinator, test_occ_ui |
| 3 | Python backend, SQLite, idempotent migrations | Preserved; additive v4 tables `agent_missions`, `agent_steps` (append-only triggers) | test_v3_foundation, test_v4_web |
| 4 | AI parsing chain Gemini → Groq → rules; 8 s timeout; 1 retry on timeout/429/5xx; breaker after 3 | Unchanged; shown read-only on `/monitoring` with values read from code | test_round3_journey, test_v4_web::monitoring |
| 5 | 30 s alert timeout, 4-worker burst, 12-alert load test | Unchanged; burst runnable from `/monitoring` | screenshot 13 |
| 6 | Prompt-injection screening before AI | Unchanged; `/web/alerts` goes through it | test_v4_web::injection_blocked_before_ai |
| 7 | Human approval engine, 15-min journey expiry, 90 s assistance escalation, 30-min gate-move TTL | All kept as separate policies; Approval Centre labels each | test_approval, test_v4_web::journey_approval |
| 8 | n8n adapter `/v1/*` (Bearer + HMAC, SERVICE can never approve) | Same FastAPI object, same routes | test_api_security, test_v4_web::n8n_adapter |
| 9 | Deterministic flight/transfer calculations, indoor navigation, accessible routing | Reused for the 3D/2D routes and passenger directions | test_routing, test_accessibility |
| 10 | U-4.1 vulnerable first, batches of 10, batch-3 failure preserved | Same services and inputs, now via agents | test_u41 + test_v4_web::u41 |
| 11 | U-4.2 crew legality, counters immutable | Same | test_u42 + test_v4_web::u42 |
| 12 | U-4.3 sign-off validation ≠ aircraft release | Same; now two explicit phases (invalid, then valid) | test_u43 + test_v4_web::u43 |
| 13 | U-4.4 seat + bags in one transaction, injected rollback | Same | test_u44 + test_v4_web::u44 |
| 14 | U-4.5 versioned approvals, STALE + fresh proposal | Same; the approve/execute steps are real controller clicks | test_u45 + test_v4_web::u45 |
| 15 | Append-only audit + safety log export | Preserved; `/audit` with filters and CSV export | test_v4_web::audit_csv |
| 16 | Synthetic-data and demo-auth labelling | Extended to every 4.0 screen | screenshots |
| 17 | Existing deployment links / Streamlit Cloud entry point | Untouched (`streamlit_app.py`, `app.py`) | — |
