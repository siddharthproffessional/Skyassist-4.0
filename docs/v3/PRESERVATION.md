# SkyAssist 3.0 — feature preservation register

Contract: 3.0 is a strict superset of 2.0. No v2 feature removed, no v2 test deleted or weakened.

## How it was checked

1. Baseline recorded **before** any 3.0 change: `docs/baseline/v2_pytest.txt` (81 passed) and
   `docs/baseline/v2_scenarios.txt` (10/10).
2. The eight v2 test files are **byte-identical** to the 2.0 backup (checked with `cmp`). `tests/conftest.py` only
   gained two new fixtures (`ops`, `svc`) appended at the end.
3. After 3.0: the same 81 tests rerun on their own → `docs/results/v3_baseline_81_rerun.txt` (**81 passed**);
   the full suite → `docs/results/v3_pytest_full.txt` (**204 passed**); `run_scenarios.py` → **10/10**.

## v2 files touched by 3.0 (all additive)

| File | Change | Why it cannot break v2 |
|---|---|---|
| `app.py` | `/occ` page added; `ensure_seeded()` in bootstrap | existing routes unchanged; seeding only inserts the synthetic OCC dataset if absent |
| `build_db.py` | flights seed insert names its columns | **bug fix found by 3.0 tests:** positional insert would crash every restart once `flights.aircraft_reg` exists |
| `database/migrations.py` | calls `migrate_v3`, records schema 3 | v3 migration is `IF NOT EXISTS` / `INSERT OR IGNORE` only |
| `services/coordinator_service.py` | gate change also bumps resource versions + audit + outbox | skipped when v3 tables are absent; v2 behaviour and notifications unchanged |
| `views/coordinator.py`, `views/operations.py` | one sidebar link to the OCC | |
| `views/passenger.py` | rebooking & baggage card on the Flights tab | rendered only when the booking has 3.0 data; wrapped so it can never break the page |
| `tests/conftest.py` | `ops` and `svc` fixtures appended | existing fixtures untouched |

## Register

| # | 2.0 feature | Status in 3.0 | Evidence |
|---|---|---|---|
| 1 | Passenger portal `/passenger` (mobile) | Preserved + baggage card | test_passenger_journey (15), test_integration UI smoke, screenshot `pax_01_…` |
| 2 | Coordinator portal `/coordinator` | Preserved + OCC link | test_coordinator (7) |
| 3 | Operations page `/operations` | Preserved + OCC link | test_integration |
| 4 | Landing page `/` | Preserved | router unchanged |
| 5 | Backend RBAC (Principal, require_role, booking access) | Preserved; extended with SERVICE identity | test_permissions (6), test_v3_foundation |
| 6 | PBKDF2 demo auth, env-set passwords | Preserved | test_permissions |
| 7 | Dijkstra routing STANDARD / STEP_FREE / CART; S1 = 1,900 m | Preserved | test_routing (10) |
| 8 | Accessibility constraints (step-free, lifts) | Preserved | test_accessibility (6) |
| 9 | Indoor navigation, map, steps, recalc | Preserved | test_passenger_journey |
| 10 | Approval engine (asyncio Futures, exactly-once decide, escalation never approves) | Preserved | test_approval (12) |
| 11 | Durable request lifecycle + dispatch | Preserved | test_approval, test_coordinator |
| 12 | Notifications feed | Preserved; 3.0 writes REBOOKED / GATE_CHANGE into the same table | test_u44, test_occ_ui |
| 13 | Simulator: gate change, corridor close/reopen | Preserved; gate change now also versioned | test_coordinator, test_u45 (`v2_coordinator_gate_change_also_stales_approvals`) |
| 14 | LLM chain Ollama → Gemini → Groq → rules with guard | Preserved, untouched | test_existing_scenarios (18) |
| 15 | v1 scenarios S1–S10 | Preserved | run_scenarios.py 10/10 |
| 16 | Idempotent migrations, v1 data preserved | Preserved; v3 added | test_integration, test_v3_foundation |
| 17 | Audit log (`audit_log`) | Preserved; `audit_events` added beside it | |
| 18 | Synthetic-data labelling, demo-auth labelling | Preserved and extended to the OCC | screenshots |

## Before / after

| Measure | 2.0 | 3.0 |
|---|---|---|
| Portals / routes | 4 | 5 (`/occ` added) |
| Python tests | 81 passed | 204 passed (81 original + 123 new) |
| v2 tests deleted or edited | — | 0 |
| v1 scenarios | 10/10 | 10/10 |
| Schema version | 2 | 3 (additive) |
| Red-team attacks blocked | — | 20/20 |
| n8n workflows | — | 5, imported and run end to end on n8n 2.48.7 |
| External API | none | FastAPI adapter (Bearer + HMAC) |
