# SkyAssist 4.0: 2½-minute judge demo

**Before judging:** start `uvicorn api.server:app --port 8600`. Open `http://127.0.0.1:8600` in Chrome at full
screen and sign in as `sarah` / `coord123`. Open `/demo` once and click **Start** so the synthetic data is fresh.
If the laptop struggles, press **2D** in the twin toolbar.

## First 10 seconds: visual impact (`/occ`)
"This is a live 3D digital twin of a 62-gate hub. Every colour comes from our database. Red aircraft are
cancelled or blocked flights, amber ones need a decision, and the cyan lines are real transfer routes from our
routing engine."

## Next 20 seconds: the operational story
Point at the left panel, which answers five questions: *what happened, who is affected, what the AI is doing,
whether approval is needed, and what happened next*. Click **SA-560** in the alerts. The camera flies to the red
aircraft, and the panel shows 40 bookings, 6 of them vulnerable from recorded needs only.

## Next 2 minutes: prove the agents work (`/demo`)
1. **Identify.** Two cancellations are shown, with the heatmap on.
2. **Investigate.** Eight specialist agents call read-only tools, each recorded with its latency. "Nothing has changed yet."
3. **Recover.** The SA-560 rebooking commits automatically: vulnerable passengers first, then batches of 10.
   The SA-591 rebooking **pauses**, because the bags cannot make a 35-minute connection against a 45-minute minimum.
4. **Human decision.** Read the card aloud: recommendation, Python validations, what will change, what happens if
   declined, the 15-minute expiry. Then click **APPROVE**.
5. **Result.** The amber baggage line appears in the twin. The family is on SA-592 and their bags are on SA-594.
   Show the audit trail.

## If you have more time
* `/recovery` → **Gate conflict / stale approval**: stage, approve, simulate SA-880 taking B07, then execute.
  The result is **STALE**, the action is refused, and a fresh proposal is staged.
* `/agents` → **Run permission boundary test**: 5/5 unauthorised tool calls are refused by the runtime and audited.
* `/monitoring`: the provider chain, timeouts and circuit breaker are read from the code. Run the 12-alert burst.
* Passenger phone view: `/passenger/login`, booking `PNRBAG`. It says plainly that the bags will not arrive with
  the passengers.

## Lines to keep honest
Synthetic data with illustrative geometry. There is no live tracking, and movement is animated only in labelled
simulation. No agent can approve, execute, change duty limits or release an aircraft. Omniverse is a prepared
interface, not a live connection.
