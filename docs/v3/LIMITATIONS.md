# SkyAssist 3.0 — limitations (honest)

- **All operational data is synthetic.** Flights, crew, rosters, engineers, licences, defects, seats and bags are
  invented. No AODB, crew-roster, MRO, DCS or baggage system is connected.
- **Duty limits are not real regulation.** `DEMO-FDP` is a labelled synthetic profile. A real deployment must load
  the operator's approved FTL scheme from an authoritative source; until then the system fails closed (UNKNOWN).
- **Bag minimum connection time (45 min) is the challenge's figure**, stored as a synthetic policy.
- **Maintenance "final release" is out of scope.** SkyAssist only lifts its own hold; it never issues a CRS.
- **n8n was verified locally**, not on the public demo. The Streamlit Cloud deployment runs the outbox in
  local-simulation mode and the OCC labels it that way.
- **Single SQLite database.** Fine for a pilot; production would use PostgreSQL with row-level locking.
  `BEGIN IMMEDIATE` serialises writers, which is correct but limits throughput.
- **Seat-conflict and failure injection** are simulator features, clearly marked in the audit trail as
  `SIMULATED_SEAT_CONFLICT` / injected failures.
- **Demo identities.** `sarah`/`aisha` and passenger accounts are demo accounts, not production identity. The API's
  service token is a shared secret; production would use mTLS or OAuth client credentials and secret rotation.
- **Performance numbers** in `PERFORMANCE.md` are one machine's measurements, not capacity claims.
- **No LLM in OCC decisions** by design. The v2 chat assistant is unchanged.
