"""Idempotent schema migrations for SkyAssist 2.0.

Every migration can run any number of times on a v1 or v2 database without losing data:
tables use CREATE TABLE IF NOT EXISTS, new columns are added only when missing, seeds use INSERT OR IGNORE.
"""
import json
import os

from db import connect, utcnow

SCHEMA_VERSION = 3

V2_TABLES = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INT PRIMARY KEY, applied_at TEXT);

CREATE TABLE IF NOT EXISTS terminal_nodes(
    node_id TEXT PRIMARY KEY, name TEXT, node_type TEXT, concourse TEXT, floor INT, x REAL, y REAL);
CREATE TABLE IF NOT EXISTS terminal_edges(
    edge_id TEXT PRIMARY KEY, from_node TEXT, to_node TEXT, distance_m REAL, estimated_walk_time REAL,
    accessible INT, stairs INT, escalator INT, elevator INT, restricted INT, cart_ok INT,
    direction_description TEXT, kind TEXT, geometry TEXT, available INT DEFAULT 1, closure_reason TEXT);
CREATE TABLE IF NOT EXISTS gate_locations(gate_id TEXT PRIMARY KEY, node_id TEXT, concourse TEXT, floor INT);

CREATE TABLE IF NOT EXISTS navigation_routes(
    route_id INTEGER PRIMARY KEY AUTOINCREMENT, booking_ref TEXT, origin_node TEXT, dest_gate TEXT,
    profile TEXT, distance_m REAL, steps_json TEXT, path_json TEXT, accessible_verified INT,
    graph_version TEXT, reason TEXT, created_at TEXT, superseded_at TEXT);
CREATE TABLE IF NOT EXISTS route_progress(
    booking_ref TEXT PRIMARY KEY, route_id INT, step_index INT DEFAULT 0, started INT DEFAULT 0,
    origin_override TEXT, location_source TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS users(
    username TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('PASSENGER','COORDINATOR')),
    display_name TEXT, password_hash TEXT, salt TEXT, booking_ref TEXT, active INT DEFAULT 1, created_at TEXT);

CREATE TABLE IF NOT EXISTS request_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, event_type TEXT, actor TEXT, detail TEXT,
    created_at TEXT);
CREATE TABLE IF NOT EXISTS notification_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_ref TEXT, request_id TEXT, kind TEXT, message TEXT,
    created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, detail TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS staff(
    staff_id TEXT PRIMARY KEY, name TEXT, role TEXT, status TEXT DEFAULT 'AVAILABLE');
CREATE TABLE IF NOT EXISTS mobility_resources(
    resource_id TEXT PRIMARY KEY, kind TEXT, label TEXT, status TEXT DEFAULT 'AVAILABLE');
"""

NEW_REQUEST_COLUMNS = {
    "created_at_utc": "TEXT",
    "updated_at_utc": "TEXT",
    "resolved_at_utc": "TEXT",
    "escalated_at": "TEXT",
    "dispatch_status": "TEXT DEFAULT 'NONE'",
    "assigned_staff_id": "TEXT",
    "assigned_resource_id": "TEXT",
    "hold_minutes_approved": "INT DEFAULT 0",
    "source": "TEXT DEFAULT 'AGENT'",
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_flights_gate ON flights(gate)",
    "CREATE INDEX IF NOT EXISTS ix_req_status ON dispatch_requests(status)",
    "CREATE INDEX IF NOT EXISTS ix_req_booking ON dispatch_requests(booking_ref)",
    "CREATE INDEX IF NOT EXISTS ix_req_events ON request_events(request_id)",
    "CREATE INDEX IF NOT EXISTS ix_notif_booking ON notification_events(booking_ref)",
    "CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(conv_id)",
    "CREATE INDEX IF NOT EXISTS ix_trace_conv ON trace(conv_id)",
    "CREATE INDEX IF NOT EXISTS ix_routes_booking ON navigation_routes(booking_ref)",
]

STAFF = [("ST-01", "Ahmed K.", "PRM agent"), ("ST-02", "Maria L.", "PRM agent"),
         ("ST-03", "Ravi P.", "Cart driver"), ("ST-04", "Chen W.", "Escort (minors)")]
RESOURCES = [("CART-01", "CART", "Mobility cart 1"), ("CART-02", "CART", "Mobility cart 2"),
             ("CART-03", "CART", "Mobility cart 3"), ("WCH-01", "WHEELCHAIR", "Wheelchair 1"),
             ("WCH-02", "WHEELCHAIR", "Wheelchair 2"), ("WCH-03", "WHEELCHAIR", "Wheelchair 3")]


def _columns(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def migrate():
    con = connect()
    try:
        con.executescript(V2_TABLES)
        have = _columns(con, "dispatch_requests")
        for col, ddl in NEW_REQUEST_COLUMNS.items():
            if col not in have:
                con.execute(f"ALTER TABLE dispatch_requests ADD COLUMN {col} {ddl}")
        # backfill v1 rows: status time in UTC, durable dispatch state
        con.execute("UPDATE dispatch_requests SET created_at_utc = strftime('%Y-%m-%dT%H:%M:%S+00:00', created_at, "
                    "'unixepoch') WHERE created_at_utc IS NULL AND created_at IS NOT NULL")
        con.execute("UPDATE dispatch_requests SET dispatch_status='NONE' WHERE dispatch_status IS NULL")
        for ix in INDEXES:
            con.execute(ix)
        _seed_graph(con)
        _seed_resources(con)
        _seed_users(con)
        con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(?,?)", (2, utcnow()))
        from database.migrations_v3 import migrate_v3
        migrate_v3(con)                      # SkyAssist 3.0 — additive, idempotent
        con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(?,?)", (SCHEMA_VERSION, utcnow()))
        con.commit()
    finally:
        con.close()


def _seed_graph(con):
    from services.routing_engine import build_synthetic_graph, gate_node
    nodes, edges = build_synthetic_graph()
    con.executemany("INSERT OR IGNORE INTO terminal_nodes VALUES(:node_id,:name,:node_type,:concourse,:floor,:x,:y)",
                    nodes)
    con.executemany(
        "INSERT OR IGNORE INTO terminal_edges(edge_id,from_node,to_node,distance_m,estimated_walk_time,accessible,"
        "stairs,escalator,elevator,restricted,cart_ok,direction_description,kind,geometry) VALUES(:edge_id,"
        ":from_node,:to_node,:distance_m,:estimated_walk_time,:accessible,:stairs,:escalator,:elevator,:restricted,"
        ":cart_ok,:direction_description,:kind,:geometry)", edges)
    for r in con.execute("SELECT gate, concourse FROM gates").fetchall():
        con.execute("INSERT OR IGNORE INTO gate_locations VALUES(?,?,?,1)", (r[0], gate_node(r[0]), r[1]))


def _seed_resources(con):
    con.executemany("INSERT OR IGNORE INTO staff(staff_id,name,role) VALUES(?,?,?)", STAFF)
    con.executemany("INSERT OR IGNORE INTO mobility_resources(resource_id,kind,label) VALUES(?,?,?)", RESOURCES)


def _seed_users(con):
    """DEMONSTRATION accounts only. Passwords come from env vars; hashes are PBKDF2-SHA256."""
    from services.auth_service import hash_password
    pax_pw = os.getenv("PASSENGER_DEMO_PASSWORD", "demo123")
    coord_pw = os.getenv("COORDINATOR_DEMO_PASSWORD", "coord123")
    for r in con.execute("SELECT booking_ref, lead_name FROM passengers").fetchall():
        if not con.execute("SELECT 1 FROM users WHERE username=?", (r[0],)).fetchone():
            h, salt = hash_password(pax_pw)
            con.execute("INSERT INTO users VALUES(?,?,?,?,?,?,1,?)",
                        (r[0], "PASSENGER", r[1], h, salt, r[0], utcnow()))
    for username, name in (("aisha", "Coordinator Aisha"), ("sarah", "Coordinator Sarah")):
        if not con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            h, salt = hash_password(coord_pw)
            con.execute("INSERT INTO users VALUES(?,?,?,?,?,NULL,1,?)",
                        (username, "COORDINATOR", name, h, salt, utcnow()))


def schema_report():
    con = connect()
    try:
        return {r[0]: sorted(_columns(con, r[0])) for r in
                con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        con.close()


if __name__ == "__main__":
    migrate()
    print(json.dumps(schema_report(), indent=1))
