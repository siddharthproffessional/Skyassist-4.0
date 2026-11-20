# SkyAssist 3.0 — test results (actual runs)

Raw outputs are saved next to this file in `docs/results/` and `docs/baseline/`.

| Run | Command | Result | Raw output |
|---|---|---|---|
| 2.0 baseline (before 3.0) | `python -m pytest -q` | 81 passed | `docs/baseline/v2_pytest.txt` |
| 2.0 scenarios (before) | `python run_scenarios.py` | 10/10 | `docs/baseline/v2_scenarios.txt` |
| 2.0 tests rerun on 3.0 | `pytest tests/test_{existing_scenarios,routing,accessibility,approval,permissions,passenger_journey,coordinator,integration}.py` | **81 passed** | `docs/results/v3_baseline_81_rerun.txt` |
| Full 3.0 suite | `python -m pytest -q` | **204 passed** | `docs/results/v3_pytest_full.txt` |
| Scenarios on 3.0 | `python run_scenarios.py` | **10/10** | `docs/results/v3_scenarios.txt` |
| Red team | `python scripts/redteam.py` | **20/20 blocked** | `docs/REDTEAM.md` |
| Performance | `python scripts/perf.py` | measured | `docs/PERFORMANCE.md` |
| Real n8n end to end | `python scripts/n8n_e2e.py` | **7/7 checks pass** | `docs/results/n8n_e2e.md` |

## New tests by area (123)

| File | Tests | What it proves |
|---|---:|---|
| test_v3_foundation.py | 9 | additive/idempotent migration, append-only audit, immutable rules and sign-offs, idempotency keys, safe demo reset |
| test_u41_rebooking.py | 13 | priority transaction first, batches 10/10/10/4, batch-3 isolation, retry on fresh availability, escalation, no double booking, idempotent jobs |
| test_u42_crew.py | 11 | 20 vs 40 min → ILLEGAL, message is data, reserves ranked, re-validation at execution, UNKNOWN fails closed, no write path |
| test_u43_maintenance.py | 14 | unlicensed + pre-defect → INVALID and blocked, record preserved, each check isolated, valid clears defect only |
| test_u44_baggage.py | 13 | 35 vs 45 min, atomic commit, rollback at 4 injection points, refusal when no bag flight, idempotent replay |
| test_u45_stale.py | 12 | B7 reassigned → STALE + re-stage, double execution, target swap, expiry, snapshot hash, v2 gate change, workflow E |
| test_api_security.py | 14 | token, HMAC, tampering, strict schemas, idempotency, 403 on approve, replay 409, no secrets in DB |
| test_n8n_workflows.py | 12 | five exports, structure, no secrets, env-only, generator reproducible |
| test_occ_ui.py | 4 | OCC sign-in gate, 7 workspaces, scenario buttons drive real services, passenger sees separate bags |
| test_redteam.py | 21 | all 20 attacks blocked inside pytest |

## Bugs the new tests found (fixed in the code, not in the tests)

1. **Restart crash** — `build_db.seed_base` inserted flights positionally; after the v3 column it failed with
   "11 columns but 10 values". Every app restart on a v3 database would have crashed. Fixed with explicit columns.
2. **Lost refusal record** — a crew approval refused at execution raised inside its transaction, so the
   `REFUSED_ILLEGAL` status and audit row were rolled back. Now committed first, then raised.
