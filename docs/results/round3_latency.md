# Round 3 — measured latency (SkyAssist processing only)

`python scripts/round3_bench.py` · 10 runs per alert on fresh synthetic databases · Python 3.13.18 on Linux x86_64 · AI step in rules mode, so these numbers exclude provider latency (the live app logs provider latency per call in Monitoring).

| Alert | p50 ms | p95 ms |
|---|---:|---:|
| Cancellation (safe, automatic) | 507 | 548 |
| Cancellation with bags that can't connect (risky → approval) | 34 | 47 |
| Gate move request (risky → approval) | 25 | 31 |
| Crew message | 48 | 61 |
| Maintenance sign-off | 30 | 36 |
| Status question (read-only) | 24 | 32 |
| Prompt-injection attack | 10 | 35 |
| Malformed alert | 4 | 5 |

Burst of 12 mixed alerts on 4 workers: wall time p50 802 ms, p95 843 ms.
