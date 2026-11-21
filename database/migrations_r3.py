"""SkyAssist Round 3 — additive tables for the end-to-end alert journey and the AI gateway log.
CREATE TABLE IF NOT EXISTS only; safe to run on every start."""

R3_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, purpose TEXT, provider TEXT, model TEXT, attempt INT,
    latency_ms REAL, tokens_in INT, tokens_out INT, outcome TEXT, error TEXT, run_id TEXT);
CREATE INDEX IF NOT EXISTS ix_llm_calls_run ON llm_calls(run_id);

CREATE TABLE IF NOT EXISTS journey_runs(
    run_id TEXT PRIMARY KEY, idem_key TEXT UNIQUE, source TEXT, batch_id TEXT, actor TEXT, alert_text TEXT,
    status TEXT, alert_type TEXT, extracted TEXT, ai_provider TEXT, safety_case TEXT, outcome TEXT, summary TEXT,
    summary_source TEXT, created_at TEXT, finished_at TEXT, latency_ms REAL);
CREATE INDEX IF NOT EXISTS ix_journey_batch ON journey_runs(batch_id);

CREATE TABLE IF NOT EXISTS journey_steps(
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, seq INT, step TEXT, status TEXT, detail TEXT, ms REAL,
    created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_journey_steps_run ON journey_steps(run_id);

CREATE TABLE IF NOT EXISTS journey_approvals(
    approval_id TEXT PRIMARY KEY, run_id TEXT, action TEXT, booking_ref TEXT, flight_no TEXT, payload TEXT,
    risk_reason TEXT, status TEXT DEFAULT 'PENDING', created_at TEXT, expires_at TEXT, decided_by TEXT,
    decided_at TEXT, result TEXT);
"""

R3_POLICIES = [
    ("journey.max_alert_chars", "2000", "Longest alert text accepted", 1),
    ("journey.approval_ttl_min", "15", "Minutes a paused risky action waits before it expires (safe default)", 1),
    ("journey.run_timeout_s", "30", "Per-alert processing deadline in burst mode", 1),
]


def migrate_r3(con):
    con.executescript(R3_SCHEMA)
    from db import utcnow
    for k, v, d, verified in R3_POLICIES:
        con.execute("INSERT OR IGNORE INTO ops_policies(policy_key,value,source,verified,updated_at) "
                    "VALUES(?,?,?,?,?)", (k, v, f"SkyAssist Round 3 demo policy: {d}", verified, utcnow()))
