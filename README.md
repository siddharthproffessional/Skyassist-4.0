# ✈️ SkyAssist 2.0: connection management, indoor navigation and human-approved assistance

**University Track, Domain 4: Aviation & Airport Operations**

- 🎬 **Demo video:** [`docs/SkyAssist2_demo.mp4`](docs/SkyAssist2_demo.mp4) (79 s)
- 📝 **How it works:** [`docs/SUBMISSION.md`](docs/SUBMISSION.md)
- 🖥️ **Pitch deck (website):** [`docs/index.html`](docs/index.html), live at https://siddharthproffessional.github.io/skyassist/ once GitHub Pages is on
- 📸 **Screenshots:** [`docs/screenshots/`](docs/screenshots/)

SkyAssist 2.0 has two portals on one shared backend:

- **Passenger portal** (`/passenger`, mobile-first). Passengers see their verified next gate, the time left, an honest connection-risk rating and step-by-step indoor directions on a terminal map. They can also track their assistance request.
- **Coordinator portal** (`/coordinator`, desktop-first). Airport staff get a live queue of requests ordered by risk, the passenger's route on the same map, deterministic calculations, approve/decline decisions recorded exactly once, staff and cart assignment, and a full audit history.

The design rule is the same as in v1: **the AI assists, deterministic code calculates, a human authorises, and the passenger always gets truthful information.**

> All data is **synthetic demonstration data**. No live flight feed, indoor positioning or dispatch system is connected, and the UI says so wherever it matters.

---

## Quick start

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py                 # builds the synthetic DB on first run, migrations after that
```

| Route | Who | Demo sign-in (synthetic) |
|---|---|---|
| `http://localhost:8501/` | Landing page | n/a |
| `/passenger` | Passenger | Booking `PNR1A2` (S1 family), password `demo123` |
| `/coordinator` | Coordinator | `sarah` or `aisha`, password `coord123` |
| `/operations` | Coordinator | Connection board, synthetic-data simulator, audit log |

Passwords come from `PASSENGER_DEMO_PASSWORD` and `COORDINATOR_DEMO_PASSWORD` (see `.env.example`) and are stored PBKDF2-hashed. **This is demonstration authentication, not production identity verification.**

Optional LLM: Ollama `qwen3` → `GEMINI_API_KEY` → `GROQ_API_KEY` → offline rules mode. Everything works with no LLM at all.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q                   # 81 tests: unit, integration, concurrency, Streamlit UI smoke
python run_scenarios.py               # original S1–S10 in the terminal → 10/10
# browser demo (app running on a fresh DB):
python tests/e2e_browser_demo.py shots approve      # or: decline
```

**Latest results:** `81 passed` · `run_scenarios.py` 10/10 · browser demo: approve and decline flows both pass, with no page errors.

---

## Architecture

```
 PASSENGER UI (views/passenger.py)          COORDINATOR UI (views/coordinator.py, views/operations.py)
        │  mobile-first, polling fragments             │  desktop-first, live queue
        ▼                                              ▼
 passenger_service ── assistance_service      coordinator_service   (every call checks the Principal's role)
        │                    │                         │
        └──────────── SHARED SKYASSIST SERVICES ───────┘
   auth_service (RBAC, PBKDF2)      routing_engine (graph + Dijkstra)      tools.py (transfer maths, policy)
   navigation_service (routes, progress)    location_provider (manual; BLE/QR/UWB interfaces)
   request_store (durable lifecycle, atomic transitions)    approval.py (asyncio Futures, agent resume)
   agent.py + llm.py (language only, hallucination guard)   integrations.py (future providers, not faked)
        │
        ▼
 SQLITE (single source of truth; idempotent migrations in database/migrations.py)
```

```mermaid
flowchart LR
  P[Passenger portal] --> PS[passenger_service]
  C[Coordinator portal] --> CS[coordinator_service]
  PS --> AS[assistance_service]
  PS --> NAV[navigation_service] --> RE[routing_engine]
  PS --> T[tools.py transfer + policy] --> RE
  AS --> AE[approval engine] --> RS[(request_store / SQLite)]
  CS --> RS
  CS -- notify_decided --> AE
  AE -- resume --> AG[agent + LLM]
  AG --> RS
```

### Key design decisions
- **One routing engine for everything.** `tools.calculate_terminal_transfer_time()`, the passenger map, navigation steps and the coordinator view all use `services/routing_engine.py`. Distance always comes from summing graph edges, never straight-line distance. Every v1 number is reproduced exactly; `test_numbers_identical_to_v1` checks S1's 1,900 m and 68/34 min.
- **Accessible routing.** Wheelchair, stroller and elderly passengers get **step-free** routes (lifts, no stairs or escalators). Carts get step-free, cart-permitted routes. If no step-free route exists, the passenger sees an error and **never a silent fallback** to a walking route.
- **Durable approvals.** SQLite holds every request state. A decision is one guarded `UPDATE … WHERE status='PENDING'` inside `BEGIN IMMEDIATE`, so concurrent coordinators get exactly one winner. Only after that commit does the system wake the waiting `asyncio.Future`. After a restart, decisions are still read from the database.
- **Approval ≠ dispatch.** The passenger sees APPROVED → (staff assigned) → DISPATCHED → STAFF EN ROUTE → COMPLETED, and each step only after a coordinator records it. A timeout **escalates**; it never approves.
- **Honest risk.** The headline risk uses the *unassisted* plan until assistance is actually approved: S1 shows AT RISK, then TIGHT after approval.
- **Idempotent requests.** One active request per booking, whether it came from the policy, the chat or the passenger themselves.

### Data model (added by migration v2)
`terminal_nodes`, `terminal_edges` (accessible / stairs / escalator / elevator / restricted / cart_ok / available), `gate_locations`, `navigation_routes`, `route_progress`, `users`, `request_events`, `notification_events`, `audit_log`, `staff`, `mobility_resources`, plus new `dispatch_requests` columns (`dispatch_status`, assignment, hold minutes, UTC timestamps, escalation). All v1 tables and data are kept. Migrations are idempotent and covered by a test that runs them twice on a v1 database.

### Correction to the brief (documented)
The 2.0 brief lists S1's arrival gate as **B07**. In the dataset the family arrives at **C12**, and **B07 is the old departure gate** that changed to B14. The brief's own numbers (68 min alone, 34 min by cart, 1 min spare) are the C12 → B14 route, so the data was kept as is.

A related finding from the new graph tests: for an able-bodied walker, C12 → B14 is genuinely shorter via the mezzanine stairs (1,250 m). Step-free travellers can't use the stairs, so S1's wheelchair route stays 1,900 m.

---

## Acceptance tests → where they're covered

| # | Requirement | Test |
|---|---|---|
| 1–3 | Login, own flight, correct gate (outdated gate never used) | `test_passenger_journey.py::test_01_02_03…`, `test_03_outdated_gate_never_used` |
| 4–6 | Valid route, numbered directions, progress persists | `test_04_05…`, `test_06_progress…` |
| 7, 28 | Gate change → recalculated route + notification | `test_07_gate_change…`, `test_routing.py::test_28…` |
| 8, 27 | Wheelchair gets a verified step-free route that avoids stairs and escalators | `test_accessibility.py` |
| 9, 24 | Passenger / anonymous users can't use coordinator functions (backend-enforced) | `test_permissions.py` |
| 10–13 | Pending → approved / declined; never a false dispatch | `test_passenger_journey.py::test_10…test_13` |
| 14–17 | Coordinator login, queue, open request, route + calculations | `test_coordinator.py` |
| 18–22 | Approve / decline, notes recorded, waiting agent resumes | `test_approval.py::test_18…`, `test_19_22…` |
| 23, 35 | Duplicate and concurrent decisions → exactly one wins | `test_23…`, `test_35…` (8 threads) |
| 25, 26 | Shortest path, distance = sum of graph edges | `test_routing.py` |
| 29, 30 | No route → clear error; no destination → no fabricated route | `test_29…`, `test_30…` |
| 31–33 | Pending survives reruns, timeout ≠ approval, many pending at once | `test_approval.py` |
| 34 | Separate users' sessions and data stay isolated | `test_permissions.py::test_34…` |
| 36 | Resolved state after restart (new engine, no Futures) | `test_approval.py::test_36…` |
| S1–S10 | Original scenarios + identical v1 numbers | `test_existing_scenarios.py`, `run_scenarios.py` |
| UI | Portals render; coordinator page refuses a passenger session | `test_integration.py` (Streamlit AppTest) |

---

## Features completed
- Two separate portals on one backend with backend-enforced RBAC. Demo auth uses PBKDF2 with env-configured passwords.
- Passenger home:
  - welcome and booking
  - arriving and connecting flight cards
  - prominent gate-change badge
  - time left, transfer estimate and distance
  - COMFORTABLE / TIGHT / AT RISK with plain-language explanation
- Indoor navigation:
  - SVG terminal map (illustrative, labelled as such) showing hubs, Level 2 skywalks, outer step-free corridor, stairs, lifts and escalators, security, Transfer Desks and assistance points
  - highlighted route with direction arrows, start and destination markers, current and completed steps
  - Start navigation, Previous, Mark step completed, Recalculate, View full route
  - distance and walking time left, arrival instructions
  - manual "update my location" (not live tracking)
- Graph routing engine (Dijkstra) with STANDARD / STEP_FREE / CART profiles, closures, rerouting and clear no-route errors.
- Assistance tracker covering every state; notifications feed; passenger self-service request form.
- Chat answers from the backend: next gate, timing, "has my assistance been approved?", nearest assistance desk, running late. English and Hinglish.
- Coordinator dashboard:
  - KPIs computed from the database
  - queue sorted AT RISK → TIGHT → COMFORTABLE, then least time left
  - filters (Pending, Approved, Declined, Escalated, Wheelchair, Escort, Mobility cart, Gate hold)
- Coordinator request detail:
  - passenger and flights
  - deterministic calculation box kept separate from the guarded AI/template summary
  - route map, suggested resources, agent trace, status timeline
- Coordinator actions:
  - decisions only after an explicit "reviewed" confirmation
  - staff and cart assignment that refuses resources already in use
  - gate hold capped at 10 min
  - dispatch lifecycle
  - warning when the gate changed after the request was created
- Operations page:
  - live connection board for all bookings
  - synthetic-data simulator: gate changes, closing and reopening corridors or lifts
  - audit log
- Durable lifecycle, atomic transitions, escalation, UTC storage with local display, idempotent migrations and indexes.
- Future-ready interfaces, deliberately **not** connected: live flight provider, SkyOps Twin topology provider, BLE/QR location providers, dispatch provider, notification channels.

## Not yet implemented
- Real airport data (OpenSky / OurAirports / AODB), live indoor positioning, a real dispatch or staff system, SMS or push notifications.
- Production identity (OIDC/SAML), sessions that survive server restarts, rate limiting.
- Multi-floor detail beyond the two levels, live lift status, live crowding or queue times at security.
- Stretch goals from v1: baggage and mobility-aid delivery tracker, quiet-room finder, audio guidance cards.
- Arabic/Urdu UI (the chat handles English and Hinglish; other languages depend on the LLM).

## Known limitations and production readiness
- **The terminal clock is simulated** per scenario, so "time remaining" doesn't count down. A real deployment would use the actual clock and flight feed.
- **Streamlit refreshes by polling** every 3–5 s, which is fine for a pilot. A large airport would want push updates and a separate API layer, and the services layer is already UI-independent to allow that.
- **SQLite** with WAL handles a single-site pilot. Moving to PostgreSQL means swapping `db.py` and the migration runner; the SQL is standard apart from `INSERT OR IGNORE`.
- **The approval Futures live in the Streamlit process.** Durable state is in SQLite, so a restart loses only the in-chat "resume" message, not the decision. The portal and notifications always reflect the stored decision.
- **Coordinates are schematic, not surveyed.** Distances reproduce the v1 dataset.
- **Readiness: a credible pilot-grade MVP, not production.** Before production it needs a security review, real identity, hosted infrastructure, monitoring, accessibility testing with real users, and validation of the walking-speed and buffer constants with airport operations staff.

## Project layout
```
app.py                      router (st.navigation): /, /passenger, /coordinator, /operations
views/                      home.py, passenger.py, coordinator.py, operations.py
components/                 ui.py (design system), airport_map.py (SVG map), session.py (sign-in)
services/                   routing_engine, navigation_service, passenger_service, assistance_service,
                            coordinator_service, request_store, auth_service, location_provider, integrations
database/migrations.py      idempotent schema v2 + seeds (graph, staff, carts, demo users)
agent.py llm.py tools.py approval.py db.py build_db.py run_scenarios.py   (v1 core, extended)
tests/                      81 pytest tests + e2e_browser_demo.py
```
