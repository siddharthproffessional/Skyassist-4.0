# SkyAssist 3.0 — database schema (migration v3)

`database/migrations_v3.py` is **additive and idempotent**: `CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE` for
policies, and one optional column (`flights.aircraft_reg`). No v1/v2 table is dropped or rewritten, and existing
rows are never overwritten. `schema_migrations` records version 3.

| Area | Tables |
|---|---|
| Shared | `audit_events` (append-only via triggers), `idempotency_records`, `resource_versions`, `workflow_outbox`, `workflow_runs` (UNIQUE workflow+execution_id), `operational_alerts`, `ops_policies` |
| U-4.1 / U-4.4 | `flight_ops`, `seat_inventory`, `seat_reservations` (UNIQUE booking+flight), `rebooking_jobs` (UNIQUE idem_key), `rebooking_batches`, `rebooking_batch_items`, `rebooking_transactions`, `passenger_rebooking_history`, `baggage_items`, `baggage_capacity` (CHECK used ≤ capacity), `bag_flight_assignments` (one ACTIVE row per bag tag), `baggage_delivery_notes` |
| U-4.2 | `crew_members`, `crew_qualifications`, `duty_rule_profiles` (no UPDATE trigger), `crew_duty_records`, `flight_crew`, `crew_messages`, `crew_assignment_proposals`, `departure_holds` (one ACTIVE hold per flight+type) |
| U-4.3 | `aircraft`, `aircraft_defects`, `maintenance_engineers`, `maintenance_evidence`, `maintenance_signoffs` (core fields immutable; status settable only from PENDING_VALIDATION; no DELETE; `dataset_epoch`), `maintenance_validation_events` |
| U-4.5 | `approval_requests` (snapshot, snapshot_hash, expected_versions, expires_at, parent_id, superseded_by), `approval_decisions`, `operational_actions` (UNIQUE approval_id) |

## Integrity enforced by the database itself

| Rule | Mechanism |
|---|---|
| Audit cannot be edited or deleted | `trg_audit_no_update`, `trg_audit_no_delete` |
| Duty limits cannot change from SkyAssist | trigger blocks UPDATE on `duty_rule_profiles` |
| Sign-off records cannot be rewritten or deleted | triggers on `maintenance_signoffs` |
| A seat cannot be sold twice | PK (flight, seat) + CAS `UPDATE … WHERE status='AVAILABLE'` |
| A passenger cannot hold two seats on one flight | UNIQUE(booking_ref, flight_no) |
| Bag capacity cannot be exceeded | CHECK + CAS `WHERE used+n<=capacity` |
| An approval executes at most once | UNIQUE(approval_id) in `operational_actions` |
| A workflow execution is processed at most once | UNIQUE(workflow, execution_id) |

## Policies (`ops_policies`)

| Key | Value | Source / status |
|---|---|---|
| rebooking.batch_size | 10 | OCC policy from the challenge |
| rebooking.max_retries | 2 | SkyAssist demo policy |
| rebooking.vulnerable_needs | WCHR, UMNR, ELDERLY | recorded booking needs only — never inferred |
| baggage.min_transfer_min | 45 | **synthetic** demo minimum from the challenge |
| approvals.gate_move_ttl_min | 30 | demo policy |
| demo.epoch | counter | synthetic reset generation |

The crew profile `DEMO-FDP` (600 min duty, 600 min rest) is **synthetic demonstration data, not a real
regulation**. `UNVERIFIED-OSL` has no verified values, so every check against it returns UNKNOWN and fails closed.
