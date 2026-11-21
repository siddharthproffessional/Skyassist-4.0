# SkyAssist 4.0 — test and QA results (measured 2026-11-21)

## Backend

| Suite | Result | File |
|---|---|---|
| Baseline before 4.0 | 239 passed | `baseline/pytest_baseline.txt` |
| Full suite after 4.0 (239 original + 25 new) | **264 passed** | `pytest_full_v4.txt` |
| Original ten passenger scenarios S1–S10 | **10/10** | `scenarios_v4.txt` |
| Original test files changed | **0** (SHA-256 compared) | `baseline/tests_sha256_before.txt` |

New tests (`tests/test_v4_web.py`, 25): sign-in required, CSRF header, passenger cannot reach OCC or approve, wrong
password, n8n adapter still refuses approvals, layout keeps the 62 gates and graph distances, flight→gate relations,
gate/flight detail, corridor closure recalculates routes, U-4.1…U-4.5 through agents and the Approval Centre
(including the full stale-approval human flow), boundary refusals audited, no agent owns a human-only tool,
`agent_steps` append-only, agent status reflects recorded steps, injection blocked before AI, journey approval,
audit CSV + monitoring values, passenger portal truthfulness, reset, delay event, geometry-source contract.

## Browser QA (real Chromium, `scripts/qa_browser_v4.py`)

Every flow was driven through the UI against the production build served by `api/server.py`:
OCC (3D), selected flight, selected gate, Agent Mission Control, Recovery Simulator (all five U-4 flows + corridor
closure + delay), Approval Centre, monitoring with a real 12-alert burst, audit, 2D fallback, the five-stage guided
demo including a real APPROVE click, and the passenger portal at 390×844. Screenshots: `screenshots/01…21`.
No uncaught page errors were recorded in the final run.

Visual checks done on the screenshots: text readability, panel overlap (aircraft tags are kept under the panels),
clipping (gate labels raised above pier roofs, status bar no-wrap), colour never used alone (chips carry a glyph and
text; gates carry a text status in the scene).

## Performance — measured

API latency on the demo machine (2 vCPU container, SQLite, rules-only), `scripts/bench_v4.py`, n=40 each:
see `results_api_latency.md` (`/web/twin/state` p50 ≈ 37 ms, p95 ≈ 45 ms; all other endpoints < 20 ms p95).

Frontend bundle: largest chunk 1.46 MB raw / ≈450 KB gzip (three.js + R3F + postprocessing).

**Not measured:** frame rate on the target demo hardware. QA ran with software WebGL (SwiftShader), which says nothing
about GPU frame rate. The scene has a `PerformanceMonitor` that drops shadows and ambient occlusion automatically,
and a 2D mode. Benchmark on the presentation laptop before the demo (open `/occ/`, Chrome DevTools → Rendering →
FPS meter).
