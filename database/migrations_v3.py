"""Schema v3 — SkyAssist 3.0 operations platform (additive, idempotent).

Nothing in v1/v2 is dropped or rewritten. New tables only, plus one optional column on `flights`
(aircraft_reg). Safety-critical records are protected by SQLite triggers:
  * audit_events            append-only (no UPDATE, no DELETE)
  * duty_rule_profiles      immutable limits (no UPDATE)
  * maintenance_signoffs    core fields immutable, no DELETE (validation_status/reasons may be set once)
"""

V3_SCHEMA = """
-- ---------------------------------------------------------------- shared foundation
CREATE TABLE IF NOT EXISTS audit_events(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, actor TEXT NOT NULL,
    module TEXT, event_type TEXT NOT NULL, entity_type TEXT, entity_id TEXT, old_state TEXT, new_state TEXT,
    txn_id TEXT, reason TEXT, result TEXT);
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update BEFORE UPDATE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete BEFORE DELETE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;

CREATE TABLE IF NOT EXISTS idempotency_records(
    idem_key TEXT PRIMARY KEY, operation TEXT NOT NULL, request_hash TEXT, result TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS resource_versions(
    resource_id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 1, state TEXT, updated_at TEXT, last_event TEXT);
CREATE TABLE IF NOT EXISTS workflow_outbox(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT, status TEXT DEFAULT 'PENDING',
    attempts INTEGER DEFAULT 0, created_at TEXT, sent_at TEXT, last_error TEXT);
CREATE TABLE IF NOT EXISTS workflow_runs(
    run_id INTEGER PRIMARY KEY AUTOINCREMENT, workflow TEXT, execution_id TEXT, status TEXT, detail TEXT,
    created_at TEXT, UNIQUE(workflow, execution_id));
CREATE TABLE IF NOT EXISTS operational_alerts(
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT, module TEXT, severity TEXT, entity_id TEXT, title TEXT,
    detail TEXT, status TEXT DEFAULT 'OPEN', created_at TEXT, acknowledged_by TEXT, acknowledged_at TEXT);
CREATE TABLE IF NOT EXISTS ops_policies(
    policy_key TEXT PRIMARY KEY, value TEXT NOT NULL, source TEXT, verified INTEGER DEFAULT 0, updated_at TEXT);

-- ---------------------------------------------------------------- U-4.1 / U-4.4 rebooking & baggage
CREATE TABLE IF NOT EXISTS flight_ops(
    flight_no TEXT PRIMARY KEY, aircraft_reg TEXT, duty_profile_id TEXT, required_duty_min INTEGER,
    dest_arrival TEXT, operation_note TEXT);
CREATE TABLE IF NOT EXISTS seat_inventory(
    flight_no TEXT, seat_no TEXT, cabin TEXT, status TEXT DEFAULT 'AVAILABLE', booking_ref TEXT,
    version INTEGER DEFAULT 1, PRIMARY KEY(flight_no, seat_no));
CREATE TABLE IF NOT EXISTS seat_reservations(
    reservation_id TEXT PRIMARY KEY, flight_no TEXT, seat_no TEXT, booking_ref TEXT, txn_id TEXT,
    status TEXT, created_at TEXT, UNIQUE(booking_ref, flight_no));
CREATE TABLE IF NOT EXISTS rebooking_jobs(
    job_id TEXT PRIMARY KEY, disrupted_flight TEXT, target_flight TEXT, status TEXT, total INTEGER,
    vulnerable INTEGER, created_by TEXT, created_at TEXT, completed_at TEXT, report TEXT, idem_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS rebooking_batches(
    batch_id TEXT PRIMARY KEY, job_id TEXT, seq INTEGER, kind TEXT, status TEXT, passenger_count INTEGER,
    attempts INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, last_error TEXT, escalated_to TEXT,
    seats_available_at_start INTEGER);
CREATE TABLE IF NOT EXISTS rebooking_batch_items(
    batch_id TEXT, booking_ref TEXT, seq INTEGER, status TEXT, seat_no TEXT, bag_plan TEXT,
    PRIMARY KEY(batch_id, booking_ref));
CREATE TABLE IF NOT EXISTS rebooking_transactions(
    txn_id TEXT PRIMARY KEY, job_id TEXT, batch_id TEXT, kind TEXT, status TEXT, detail TEXT,
    started_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS passenger_rebooking_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_ref TEXT, from_flight TEXT, to_flight TEXT, seat_no TEXT,
    txn_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS baggage_items(
    bag_tag TEXT PRIMARY KEY, booking_ref TEXT, weight_kg REAL, current_location TEXT, status TEXT,
    origin_flight TEXT);
CREATE TABLE IF NOT EXISTS baggage_capacity(
    flight_no TEXT PRIMARY KEY, capacity INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0,
    version INTEGER DEFAULT 1, CHECK(used <= capacity));
CREATE TABLE IF NOT EXISTS bag_flight_assignments(
    assignment_id TEXT PRIMARY KEY, bag_tag TEXT, booking_ref TEXT, flight_no TEXT, txn_id TEXT, kind TEXT,
    status TEXT, created_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bag_active ON bag_flight_assignments(bag_tag) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS baggage_delivery_notes(
    note_id TEXT PRIMARY KEY, booking_ref TEXT, bag_tags TEXT, carrying_flight TEXT, expected_arrival TEXT,
    delivery_destination TEXT, txn_id TEXT, status TEXT, created_at TEXT);

-- ---------------------------------------------------------------- U-4.2 crew
CREATE TABLE IF NOT EXISTS crew_members(
    crew_id TEXT PRIMARY KEY, name TEXT, role TEXT, base TEXT, roster_status TEXT, availability TEXT);
CREATE TABLE IF NOT EXISTS crew_qualifications(
    crew_id TEXT, aircraft_type TEXT, licence_no TEXT, valid_until TEXT, PRIMARY KEY(crew_id, aircraft_type));
CREATE TABLE IF NOT EXISTS duty_rule_profiles(
    profile_id TEXT PRIMARY KEY, label TEXT, max_duty_min INTEGER, min_rest_min INTEGER, source TEXT,
    verified INTEGER DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS trg_duty_profile_immutable BEFORE UPDATE ON duty_rule_profiles
    BEGIN SELECT RAISE(ABORT, 'duty limits are read-only in SkyAssist'); END;
CREATE TABLE IF NOT EXISTS crew_duty_records(
    crew_id TEXT PRIMARY KEY, profile_id TEXT, elapsed_min INTEGER, rest_since_min INTEGER, source TEXT,
    recorded_at TEXT);
CREATE TABLE IF NOT EXISTS flight_crew(
    flight_no TEXT, crew_id TEXT, role TEXT, status TEXT, assigned_at TEXT, PRIMARY KEY(flight_no, crew_id));
CREATE TABLE IF NOT EXISTS crew_messages(
    msg_id INTEGER PRIMARY KEY AUTOINCREMENT, flight_no TEXT, channel TEXT, sender TEXT, body TEXT, flags TEXT,
    received_at TEXT);
CREATE TABLE IF NOT EXISTS crew_assignment_proposals(
    proposal_id TEXT PRIMARY KEY, flight_no TEXT, replace_crew_id TEXT, candidate_crew_id TEXT, role TEXT,
    required_min INTEGER, remaining_min INTEGER, validation TEXT, status TEXT, created_at TEXT,
    decided_by TEXT, decided_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS departure_holds(
    hold_id INTEGER PRIMARY KEY AUTOINCREMENT, flight_no TEXT, hold_type TEXT, reason TEXT, status TEXT,
    created_at TEXT, cleared_at TEXT, cleared_by TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_hold_active ON departure_holds(flight_no, hold_type) WHERE status='ACTIVE';

-- ---------------------------------------------------------------- U-4.3 maintenance
CREATE TABLE IF NOT EXISTS aircraft(reg TEXT PRIMARY KEY, aircraft_type TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS aircraft_defects(
    defect_id TEXT PRIMARY KEY, reg TEXT, defect_type TEXT, description TEXT, opened_at_utc TEXT, severity TEXT,
    status TEXT, restriction TEXT, cleared_by_signoff TEXT, cleared_at TEXT);
CREATE TABLE IF NOT EXISTS maintenance_engineers(
    engineer_id TEXT PRIMARY KEY, name TEXT, licence_no TEXT, licence_valid_from TEXT, licence_valid_to TEXT,
    authorised_types TEXT, scope TEXT, roster_status TEXT);
CREATE TABLE IF NOT EXISTS maintenance_evidence(
    evidence_ref TEXT PRIMARY KEY, defect_id TEXT, description TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS maintenance_signoffs(
    signoff_id TEXT PRIMARY KEY, engineer_id TEXT, defect_id TEXT, reg TEXT, task_scope TEXT, result TEXT,
    signed_at_utc TEXT, evidence_ref TEXT, record_hash TEXT, validation_status TEXT, reasons TEXT,
    submitted_at TEXT, submitted_by TEXT, dataset_epoch INTEGER DEFAULT 1);
CREATE TRIGGER IF NOT EXISTS trg_signoff_core_immutable
    BEFORE UPDATE OF engineer_id, defect_id, reg, task_scope, result, signed_at_utc, evidence_ref, record_hash,
    submitted_at, submitted_by ON maintenance_signoffs
    BEGIN SELECT RAISE(ABORT, 'maintenance sign-off records are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_signoff_status_once BEFORE UPDATE OF validation_status ON maintenance_signoffs
    WHEN OLD.validation_status != 'PENDING_VALIDATION'
    BEGIN SELECT RAISE(ABORT, 'a sign-off validation result cannot be rewritten'); END;
CREATE TRIGGER IF NOT EXISTS trg_signoff_no_delete BEFORE DELETE ON maintenance_signoffs
    BEGIN SELECT RAISE(ABORT, 'maintenance sign-off records cannot be deleted'); END;
CREATE TABLE IF NOT EXISTS maintenance_validation_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, signoff_id TEXT, check_name TEXT, passed INTEGER, detail TEXT,
    created_at TEXT);

-- ---------------------------------------------------------------- U-4.5 versioned approvals
CREATE TABLE IF NOT EXISTS approval_requests(
    approval_id TEXT PRIMARY KEY, action_type TEXT, flight_no TEXT, target_resource TEXT, action_payload TEXT,
    expected_versions TEXT, snapshot TEXT, snapshot_hash TEXT, status TEXT, requested_by TEXT, requested_at TEXT,
    decided_by TEXT, decided_at TEXT, executed_at TEXT, expires_at TEXT, stale_reason TEXT, superseded_by TEXT,
    parent_id TEXT);
CREATE TABLE IF NOT EXISTS approval_decisions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT, decision TEXT, actor TEXT, reason TEXT,
    snapshot_hash_seen TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS operational_actions(
    action_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE, action_type TEXT, executed_by TEXT, executed_at TEXT,
    result TEXT);
"""

V3_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_events(entity_type, entity_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_module ON audit_events(module)",
    "CREATE INDEX IF NOT EXISTS ix_batches_job ON rebooking_batches(job_id, seq)",
    "CREATE INDEX IF NOT EXISTS ix_seat_status ON seat_inventory(flight_no, status)",
    "CREATE INDEX IF NOT EXISTS ix_bags_booking ON baggage_items(booking_ref)",
    "CREATE INDEX IF NOT EXISTS ix_bagassign_booking ON bag_flight_assignments(booking_ref)",
    "CREATE INDEX IF NOT EXISTS ix_approvals_status ON approval_requests(status)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_status ON operational_alerts(module, status)",
    "CREATE INDEX IF NOT EXISTS ix_outbox_status ON workflow_outbox(status)",
    "CREATE INDEX IF NOT EXISTS ix_passengers_outbound ON passengers(outbound)",
]

DEFAULT_POLICIES = [
    # key, value, source, verified
    ("rebooking.batch_size", "10", "OCC policy (challenge U-4.1)", 1),
    ("rebooking.max_retries", "2", "SkyAssist demo policy", 1),
    ("rebooking.vulnerable_needs", '["WCHR", "UMNR", "ELDERLY"]', "OCC policy: recorded booking needs only", 1),
    ("baggage.min_transfer_min", "45", "SYNTHETIC demo airport minimum bag connection (challenge U-4.4)", 1),
    ("approvals.gate_move_ttl_min", "30", "SkyAssist demo policy", 1),
    ("demo.epoch", "1", "Synthetic demo dataset generation counter", 1),
]


def migrate_v3(con):
    con.executescript(V3_SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(flights)")}
    if "aircraft_reg" not in cols:
        con.execute("ALTER TABLE flights ADD COLUMN aircraft_reg TEXT")
    for ix in V3_INDEXES:
        con.execute(ix)
    from db import utcnow
    con.executemany("INSERT OR IGNORE INTO ops_policies VALUES(?,?,?,?,?)",
                    [(k, v, s, ver, utcnow()) for k, v, s, ver in DEFAULT_POLICIES])
    from database.migrations_r3 import migrate_r3
    migrate_r3(con)                      # Round 3: alert journey + AI gateway log (additive)
