# SkyAssist — deployment reality (Round 3)

An honest answer to "what will it really take to run this pilot next month?" Prices are public list prices checked
on 2026-11-21. Volumes are assumptions, labelled as such. Latency is measured.

## Who runs it

| Role | Who | Time |
|---|---|---|
| Decides on paused actions (gate moves, crew swaps, rebookings with separated bags) | OCC duty controller, already on shift | Seconds per approval |
| Owns the rules (duty profile, bag connection minimum, approval time limits) | Airline crew control and ground ops, signed off by safety | Set once, reviewed quarterly |
| Runs the platform (deploys, keys, backups, monitoring) | 1 platform engineer | About 0.25 FTE during the pilot |
| Feeds the data | Integration owner for AODB / roster / MRO / DCS | Pilot uses synthetic data; integration is phase 2 |

## Where it is hosted

| Part | Pilot choice | Why |
|---|---|---|
| App + API (Streamlit + FastAPI) | Container service, 2 small nodes | Two nodes so one can restart without downtime |
| n8n | Self-hosted Community Edition, 1 small container | Free, unlimited executions, keeps alert data inside the operator's cloud |
| Database | Managed PostgreSQL (replaces the demo's SQLite) | Row-level locking for more writers, backups, point-in-time restore |
| AI providers | Gemini 2.5 Flash first, Groq Llama 3.3 70B as fallback, rules as the last resort | Two independent providers; the agent still works with none |

Data residency: a UAE operator may need a UAE cloud region. Region availability and prices there must be confirmed
before signing; the figures below are list prices for the cheapest region.

## Cost

**AI cost per request** (tokens estimated from prompt size at ~4 characters per token; the live app records exact
counts from each provider's usage fields in Monitoring):

| Request | Tokens in / out | Gemini 2.5 Flash | Groq Llama 3.3 70B |
|---|---|---:|---:|
| Ops alert (intake + controller summary) | ~320 / ~170 | $0.00052 | $0.00032 |
| Passenger message (understand + reword) | ~450 / ~210 | $0.00066 | $0.00043 |
| Blocked attack or malformed alert | 0 (stopped before any AI call) | $0 | $0 |

List prices: Gemini 2.5 Flash $0.30 per 1M input / $2.50 per 1M output tokens; Groq Llama 3.3 70B $0.59 / $0.79.
Gemini's "thinking" tokens are switched off for these short extraction tasks, so they are not billed.

**Per month, pilot at one terminal** (assumed 500 ops alerts and 3,000 passenger messages a day):

| Item | Monthly |
|---|---:|
| AI: 15,000 alerts | ~$8 |
| AI: 90,000 passenger messages | ~$59 |
| App + API containers (2 × 1 GB) | ~$20 |
| n8n container (1 GB); n8n licence | ~$10; $0 |
| Managed PostgreSQL (smallest bundle) | ~$15 |
| **Total** | **≈ $112/month ≈ $0.001 per request** |

At 10× the volume (a whole hub) the AI line grows to about $670/month; infrastructure grows more slowly.

## How fast it responds (measured)

Measured with `scripts/round3_bench.py`, 10 runs each, AI step excluded (see
[`results/round3_latency.md`](results/round3_latency.md)):

| Work | p50 | p95 |
|---|---:|---:|
| Status question, sign-off check, gate request, crew check | 24–48 ms | 31–61 ms |
| Cancellation: 40 passengers rebooked in 5 transactions, notified | 507 ms | 548 ms |
| Attack blocked | 10 ms | 35 ms |
| Burst of 12 mixed alerts, 4 workers | 802 ms wall | 843 ms wall |

AI calls add the provider's response time on top (shown per call in the OCC Monitoring tab). Each call has an 8 s
timeout and one retry, so a dead provider costs at most about 1 s before fallback once its circuit breaker is open.

## Monitoring

- `GET /health` on the API for uptime checks; the OCC Monitoring tab shows typical and slowest response time, AI
  success and fallback counts, tokens and cost.
- Every AI attempt is logged (provider, latency, tokens, outcome); every action, refusal and approval is in the
  append-only audit trail.
- Alerts in the OCC for blocked attacks, paused actions, escalations and invalid sign-offs.

## What it still cannot do

- **No live data yet.** Flights, crew, licences, defects, seats and bags are synthetic. Connecting the AODB, crew
  roster, MRO and DCS is the main work of the pilot.
- **Duty rules are a demo profile.** The airline's approved FTL scheme must be loaded and verified; until then
  SkyAssist fails closed (UNKNOWN → departure blocked).
- **Demo sign-in.** Production needs the operator's single sign-on and role mapping.
- **SQLite in the demo.** Fine for one server; the pilot moves to PostgreSQL.
- **English alerts tested most.** Other languages pass through the AI step but are not yet evaluated.
- **The injection screen is pattern-based.** It blocks the known attack shapes we tested (20/20 + 5 journey
  attacks); new shapes need new patterns. The second line of defence is that the AI can't act: it only extracts
  fields, and code validates them.
- **No final release decisions.** SkyAssist never releases an aircraft or approves its own proposals.
