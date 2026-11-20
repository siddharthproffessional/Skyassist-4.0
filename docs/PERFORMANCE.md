# SkyAssist 3.0 — measured performance

Measured by `python scripts/perf.py` — 5 runs each on a fresh synthetic SQLite database; Python 3.13.18, Linux x86_64. Timings are wall-clock for the service call only (database rebuild excluded). They describe this run on this machine, not a guarantee.

| Operation | median ms | min ms | max ms |
|---|---:|---:|---:|
| U-4.1 full job: 40 pax, 5 transactions, batch-3 conflict + 2 retries + escalation | 438.3 | 399.8 | 449.2 |
| U-4.1 full job, no injected conflict | 336.2 | 314.4 | 360.4 |
| U-4.2 crew evaluation + reserve search (4 candidates) | 31.1 | 27.7 | 38.6 |
| U-4.3 invalid + valid sign-off validation | 23.6 | 20.1 | 32.3 |
| U-4.4 feasibility only | 8.3 | 7.7 | 11.2 |
| U-4.4 atomic commit (seat + 2 bags + note) | 13.2 | 11.7 | 15.6 |
| U-4.5 stage, approve, conflicting change, stale refusal + restage | 13.9 | 12.7 | 16.1 |
| Single sign-off validation | 10.1 | 8.7 | 12.4 |
