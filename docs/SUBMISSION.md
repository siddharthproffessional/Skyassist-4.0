# SkyAssist 3.0: submission summary

**Track:** University Track, Domain 4: Aviation & Airport Operations

| | Link |
|---|---|
| Live app | https://skyassist-xjyx2wd6jqei4yxmjcr3wz.streamlit.app (`/occ` → `sarah` / `coord123`; `/passenger` → `PNRBAG` / `demo123`) |
| Pitch deck (website) | https://skyassist-pitch.vercel.app |
| Demo video | `docs/SkyAssist3_demo.mp4` (108 s), also at https://skyassist-pitch.vercel.app/SkyAssist3_demo.mp4 |
| Code | https://github.com/siddharthproffessional/skyassist |

**What 3.0 adds.** An Operations Control Centre where deterministic Python decides, n8n orchestrates and a person
approves. It handles five OCC failure modes: vulnerable passengers rebooked first in their own transaction (U-4.1),
crew messages that can't override duty limits (U-4.2), maintenance sign-offs validated against evidence (U-4.3),
seat and baggage changes committed together (U-4.4) and approvals refused once the state they covered has changed
(U-4.5). 204 tests pass (the 81 2.0 tests unchanged), 20/20 red-team attacks are blocked, and the five n8n
workflows were run end to end on a real n8n instance. All data is synthetic.

Everything below describes the 2.0 passenger and coordinator portals, which 3.0 keeps in full.

---

## SkyAssist 2.0 (preserved)

**Track:** University Track, Domain 4: Aviation & Airport Operations
**Problem:** A family lands late with a tight 35-minute connection, a gate change and a grandmother who needs a wheelchair at the aircraft door.

## What it is
SkyAssist is an AI agent for tight airport connections. It has two portals on one backend:
- **Passenger portal** (`/passenger`, phone-first): the verified next gate, time left, an honest connection risk, step-by-step indoor directions on a terminal map, and a live tracker for any assistance request.
- **Coordinator portal** (`/coordinator`, desktop): a queue of assistance requests ranked by risk. For each request it shows the passenger's route, the calculation behind it, and controls to approve or decline, assign staff and carts, and record dispatch.

## How it works (the S1 journey)
1. **The passenger signs in.** SkyAssist loads the booking and checks live gate data: DXB-402 arrived at C12, and SA-218 now departs from **B14**, not the B07 printed on the boarding pass.
2. **The code calculates.** No AI is involved in this step. A graph of the terminal (62 gates, hubs, skywalks, lifts, stairs) and Dijkstra's algorithm give a **step-free** route of 1,900 m. In a wheelchair on her own she needs **68 min**; with a mobility cart, **34 min**. She has 35 min, so 1 minute is spare.
3. **The safety policy decides what's needed:** a wheelchair at the door, a mobility cart and a gate hold of up to 10 minutes. It **requests** these. The passenger sees *AT RISK* and "requested, not confirmed".
4. **The agent pauses.** The request is saved in SQLite, and the agent waits on an asyncio Future without blocking anything else.
5. **A coordinator reviews and decides.** They see the route on the map and the calculation, tick that they have reviewed it, assign staff and a cart, and approve. The decision is atomic: if eight coordinators click at once, exactly one decision counts.
6. **The passenger's phone updates on its own** to *APPROVED* and *TIGHT*, and still says staff have not been dispatched. Dispatched, en route and completed appear only when a coordinator records them.
7. **Navigation continues** step by step: distance and time left, previous step, mark step done, recalculate.

## What makes it different
- **It never states something it hasn't verified.** The LLM (Qwen3, Gemini or Groq, all optional) only reads messages and rewords replies. Any AI text that adds a gate, time or number not in the data, or says "confirmed" while a request is pending, is blocked, and the verified text is sent instead.
- **Accessibility is real routing, not a label.** A walker may take the stairs (1,250 m); a wheelchair never will (1,900 m by lift and Skywalk). If a lift fails and no step-free route exists, the passenger is told so and sent to an assistance point, never quietly given the stairs.
- **Approval is not dispatch.** A timeout escalates and never approves. A decline says plainly that no staff are coming and where to go instead.
- **It survives disruption.** Gate changes and corridor closures recalculate routes immediately and notify the passenger.

## Proof
- 81 automated tests pass, covering the passenger and coordinator flows, routing, accessibility, permissions, concurrency, restarts and migrations.
- All 10 original scenarios (S1–S10) still pass with numbers identical to v1.
- A full browser demo of the approve and decline flows runs with no errors.

## Run it
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
# passenger:   http://localhost:8501/passenger    PNR1A2 / demo123
# coordinator: http://localhost:8501/coordinator  sarah  / coord123
python -m pytest -q
```

## Honest limits
All data is synthetic, and the terminal clock is simulated. The passenger's location is the arrival gate or set by hand; there is no live tracking. Dispatch is recorded by the coordinator. Live flight data, indoor positioning and SkyOps Twin corridor status have interfaces ready, and none is faked.
