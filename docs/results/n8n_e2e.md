# n8n end-to-end run

Run on 2026-11-20 09:43 UTC against a real n8n instance at http://127.0.0.1:5678 and the SkyAssist FastAPI adapter (`scripts/n8n_e2e.py`).

| Check | Result | Detail |
|---|---|---|
| D baggage feasibility | PASS | HTTP 200, decision SEPARATE_FLIGHT, bag flight SA-594 |
| B crew message | PASS | HTTP 200, C-101 ILLEGAL, counters unchanged True |
| C maintenance sign-off | PASS | HTTP 200, INVALID, departure blocked True |
| A disruption rebooking | PASS | HTTP 200, COMPLETED, 40 committed, vulnerable 6 |
| E state-change revalidation | PASS | HTTP 200, approval APR-9C588D13 → STALE |
| Forged signature rejected by n8n | PASS | HTTP 500 |
| Calls recorded with n8n execution ids | PASS | SkyAssist B exec 2; SkyAssist C exec 3; SkyAssist A exec 4; SkyAssist E exec 5 |
Note: workflow D (read-only feasibility) is not written to workflow_runs; A, B, C and E are.
