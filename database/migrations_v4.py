"""SkyAssist 4.0 — additive, idempotent migration for the agent execution record.

Only CREATE TABLE IF NOT EXISTS / INSERT OR IGNORE. No v1/v2/v3 table is changed.
The v4 marker is stored in ops_policies ('schema.v4') rather than schema_migrations so that the v3 contract
(schema_migrations MAX(version) == 3, asserted by tests/test_v3_foundation.py) is preserved unchanged.
"""
from db import utcnow

V4_TABLES = """
CREATE TABLE IF NOT EXISTS agent_missions(
    mission_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT, actor TEXT, status TEXT NOT NULL,
    summary TEXT, result TEXT, epoch INT, created_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE IF NOT EXISTS agent_steps(
    step_id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL, seq INT NOT NULL, agent_id TEXT NOT NULL,
    tool TEXT, phase TEXT, status TEXT NOT NULL, args TEXT, result_summary TEXT, detail TEXT, latency_ms REAL,
    source TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_agent_steps_mission ON agent_steps(mission_id, seq);
CREATE INDEX IF NOT EXISTS ix_agent_steps_agent ON agent_steps(agent_id, step_id);
CREATE TRIGGER IF NOT EXISTS trg_agent_steps_no_update BEFORE UPDATE ON agent_steps
BEGIN SELECT RAISE(ABORT, 'agent_steps is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_agent_steps_no_delete BEFORE DELETE ON agent_steps
BEGIN SELECT RAISE(ABORT, 'agent_steps is append-only'); END;
"""


def migrate_v4(con):
    con.executescript(V4_TABLES)
    con.execute("INSERT OR IGNORE INTO ops_policies VALUES(?,?,?,?,?)",
                ("schema.v4", "applied", "SkyAssist 4.0 migration (agent execution record)", 1, utcnow()))
