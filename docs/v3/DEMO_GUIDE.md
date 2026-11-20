# SkyAssist 3.0 — demo guide (≈6 minutes)

Start: `python -m streamlit run app.py` → open `/occ` → sign in `sarah` / `coord123` (demo account).
The KPI row and every table are read live from the database.

| Step | Do | Say / point at |
|---|---|---|
| 1 | Overview tab | "Five OCC challenges, each driven by real services. Workflow delivery shows *local simulation* here because n8n isn't connected to this deployment — we don't pretend." |
| 2 | Run **U-4.1** → Rebooking tab | P0 = 6 vulnerable passengers, committed first in their own transaction. B1, B2 committed. B3 hit a seat conflict, rolled back alone, retried twice on fresh availability, escalated. B4 still committed. 30 rebooked, 10 waiting for the controller — nobody half-booked. Click **Retry … with fresh availability**. |
| 3 | Run **U-4.2** → Crew tab | The message "captain agrees to extend duty, approved" is stored with flags and changes nothing. C-101: 20 min left vs 40 required → ILLEGAL, departure blocked. Reserves: R-201 expired type rating, R-202 wrong type, R-204 not rested, R-203 legal → proposal. Approve it: legality re-checked at execution. Switch to SA-702: unverified rules → UNKNOWN → blocked. |
| 4 | Run **U-4.3** → Maintenance tab | E-999's "OK": not on roster, no licence, signed before the defect opened → INVALID, kept unchanged, critical alert, aircraft stayed blocked. E-501's replacement passes all checks → defect cleared, aircraft *awaiting final release* (not "released"). |
| 5 | Run **U-4.4** → Baggage tab | Passenger 18 min transfer vs 20 to close → can make it. Bag connection 35 < 45 → bags go on SA-594 with a delivery note, committed in the same transaction as the seat. Open `/passenger` as `PNRBAG`/`demo123` → Flights: "Your bags will NOT travel with you." |
| 6 | Run **U-4.5** → Gates & approvals | EK-812 → B7 approved at GATE:B07 v1. SA-880 then took B7 (v2). Execution refused: STALE, with the reason. A fresh proposal (B06) waits for a **new** human decision. |
| 7 | Audit & workflows tab | Append-only audit trail and the outbox. |
| 8 | Reset | Expand **Synthetic demo reset**, tick the confirmation, reset. Only the synthetic OCC data is restored; audit, sign-offs and v2 data are kept. |

API + n8n: see `N8N.md` and `../results/n8n_e2e.md`.
