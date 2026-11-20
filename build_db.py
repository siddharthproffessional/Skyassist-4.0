"""Builds the synthetic terminal dataset -> airport_terminal_journey.sqlite

Tables
  gates               terminal gate map (concourse, position from concourse hub)
  hub_links           walking distance between concourse hubs
  flights             live arrival / departure telemetry (status, gate, boarding close)
  passengers          mobility-assistance manifest (needs codes per booking)
  scenarios           the 10 demo / test scenarios
  messages, trace, dispatch_requests   runtime tables used by the app
"""
import json
import os

import db
from db import connect

GATE_SPACING_M = 50                       # metres between consecutive gates
CONCOURSES = {"A": 20, "B": 20, "C": 22}  # number of gates per concourse
HUB_LINKS = [("A", "B", 500), ("B", "C", 600)]  # A<->C goes via B (1100 m)

# flight_no, origin, destination, direction, status, gate, previous_gate, sched, est, boarding_close
FLIGHTS = [
    # S1 – the brief: wheelchair grandmother, gate change, 35 minutes
    ("DXB-402", "BOM", "HUB", "ARRIVAL", "LANDED", "C12", None, "09:50", "09:58", None),
    ("SA-218", "HUB", "LHR", "DEPARTURE", "GATE_CHANGED", "B14", "B07", "10:50", "10:50", "10:35"),
    # S2 – solo traveller, comfortable
    ("SA-115", "CAI", "HUB", "ARRIVAL", "LANDED", "A04", None, "10:20", "10:25", None),
    ("SA-330", "HUB", "SIN", "DEPARTURE", "ON_TIME", "A09", None, "11:35", "11:35", "11:20"),
    # S3 – family with stroller and toddlers
    ("SA-507", "KHI", "HUB", "ARRIVAL", "LANDED", "C08", None, "10:05", "10:12", None),
    ("SA-611", "HUB", "CDG", "DEPARTURE", "ON_TIME", "B03", None, "11:05", "11:05", "10:50"),
    # S4 – unaccompanied minor
    ("SA-221", "AMM", "HUB", "ARRIVAL", "LANDED", "B10", None, "10:10", "10:15", None),
    ("SA-404", "HUB", "JFK", "DEPARTURE", "ON_TIME", "B18", None, "11:15", "11:15", "11:00"),
    # S5 – elderly traveller, same concourse
    ("SA-150", "MCT", "HUB", "ARRIVAL", "LANDED", "A02", None, "10:10", "10:16", None),
    ("SA-160", "HUB", "FRA", "DEPARTURE", "ON_TIME", "A18", None, "11:00", "11:00", "10:45"),
    # S6 – wheelchair, connection cannot be made even with assistance
    ("SA-909", "NBO", "HUB", "ARRIVAL", "LANDED", "C20", None, "09:30", "09:57", None),
    ("SA-777", "HUB", "SYD", "DEPARTURE", "BOARDING", "A15", None, "10:40", "10:40", "10:25"),
    # S7 – connecting flight cancelled
    ("SA-300", "DOH", "HUB", "ARRIVAL", "LANDED", "B05", None, "10:00", "10:04", None),
    ("SA-301", "HUB", "MAD", "DEPARTURE", "CANCELLED", "B11", None, "11:10", None, None),
    # S8 – unknown flight (XY-999 deliberately absent)
    ("SA-140", "BAH", "HUB", "ARRIVAL", "LANDED", "A07", None, "10:00", "10:02", None),
    # S9 – passenger quotes an outdated gate
    ("SA-612", "IST", "HUB", "ARRIVAL", "LANDED", "A06", None, "10:20", "10:26", None),
    ("SA-615", "HUB", "AMS", "DEPARTURE", "GATE_CHANGED", "C04", "B07", "11:25", "11:25", "11:10"),
    # S10 – delayed departure + wheelchair, Hinglish message
    ("SA-480", "DEL", "HUB", "ARRIVAL", "LANDED", "C15", None, "10:25", "10:36", None),
    ("SA-482", "HUB", "MAN", "DEPARTURE", "DELAYED", "B02", None, "11:15", "11:45", "11:30"),
]

# booking_ref, lead_name, party_size, needs, inbound, outbound, language
PASSENGERS = [
    ("PNR1A2", "Mehta family", 4, ["WCHR", "ELDERLY"], "DXB-402", "SA-218", "en"),
    ("PNR2B3", "Omar Haddad", 1, [], "SA-115", "SA-330", "en"),
    ("PNR3C4", "Siddiqui family", 4, ["STROLLER"], "SA-507", "SA-611", "en"),
    ("PNR4D5", "Lina K. (age 11)", 1, ["UMNR"], "SA-221", "SA-404", "en"),
    ("PNR5E6", "Fatima Al Saadi", 1, ["ELDERLY"], "SA-150", "SA-160", "en"),
    ("PNR6F7", "Wanjiru family", 2, ["WCHR"], "SA-909", "SA-777", "en"),
    ("PNR7G8", "Daniel Ruiz", 1, [], "SA-300", "SA-301", "en"),
    ("PNR8H9", "Claire Martin", 2, [], "SA-140", None, "en"),
    ("PNR9J1", "Emre Yilmaz", 1, [], "SA-612", "SA-615", "en"),
    ("PNR0K2", "Sharma family", 3, ["WCHR", "ELDERLY"], "SA-480", "SA-482", "hi"),
]

# id, title, booking_ref, demo clock, passenger message, expected decision
SCENARIOS = [
    ("S1", "Wheelchair grandmother, gate change, 35 min", "PNR1A2", "10:00",
     "Our inbound flight DXB-402 just parked at Concourse C, our connecting gate changed to B14, "
     "my grandmother needs her wheelchair at the aircraft door, and we only have 35 minutes before boarding closes!",
     "ASSIST_AND_HOLD_REQUESTED"),
    ("S2", "Solo traveller, comfortable connection", "PNR2B3", "10:30",
     "Landed on SA-115, connecting to SA-330 to Singapore. Where do I go?", "SELF_GUIDED"),
    ("S3", "Family with stroller and two toddlers", "PNR3C4", "10:15",
     "We just got off SA-507 with two toddlers and a stroller, our connection is SA-611 to Paris. Will we make it??",
     "ASSIST_REQUESTED"),
    ("S4", "Unaccompanied minor", "PNR4D5", "10:20",
     "Hi I'm 11 and travelling alone, I landed on SA-221 and need to get to SA-404 to New York", "ASSIST_REQUESTED"),
    ("S5", "Elderly traveller walks slowly", "PNR5E6", "10:20",
     "I am 78 years old and walk slowly. I arrived on SA-150 and my next flight is SA-160 to Frankfurt.",
     "ASSIST_REQUESTED"),
    ("S6", "Wheelchair, connection not feasible", "PNR6F7", "10:00",
     "Our SA-909 landed very late, my husband uses a wheelchair, we must catch SA-777 to Sydney!", "MISSED_REBOOK"),
    ("S7", "Connecting flight cancelled", "PNR7G8", "10:10",
     "Just landed SA-300, connecting on SA-301 to Madrid, which gate?", "CANCELLED_REDIRECT"),
    ("S8", "Unknown flight number (no hallucination)", "PNR8H9", "10:05",
     "We landed on SA-140, our connection is XY-999 to Paris, what gate is it?", "FLIGHT_NOT_FOUND"),
    ("S9", "Passenger quotes an outdated gate", "PNR9J1", "10:30",
     "Arrived on SA-612. My boarding pass says gate B07 for SA-615 to Amsterdam, going there now.", "SELF_GUIDED"),
    ("S10", "Delayed departure, wheelchair, Hinglish", "PNR0K2", "10:40",
     "Hum SA-480 se aaye hain, Dadi ko wheelchair chahiye, connecting flight SA-482 Manchester ki hai. Help please!",
     "ASSIST_REQUESTED"),
]


BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS gates(gate TEXT PRIMARY KEY, concourse TEXT, number INT, metres_from_hub INT);
CREATE TABLE IF NOT EXISTS hub_links(a TEXT, b TEXT, metres INT);
CREATE TABLE IF NOT EXISTS flights(flight_no TEXT PRIMARY KEY, origin TEXT, destination TEXT, direction TEXT,
    status TEXT, gate TEXT, previous_gate TEXT, sched TEXT, est TEXT, boarding_close TEXT);
CREATE TABLE IF NOT EXISTS passengers(booking_ref TEXT PRIMARY KEY, lead_name TEXT, party_size INT, needs TEXT,
    inbound TEXT, outbound TEXT, language TEXT);
CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY, title TEXT, booking_ref TEXT, now TEXT, message TEXT,
    expected TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, role TEXT, text TEXT,
    ts REAL DEFAULT (strftime('%s','now')));
CREATE TABLE IF NOT EXISTS trace(id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, actor TEXT, step TEXT,
    detail TEXT, ts REAL DEFAULT (strftime('%s','now')));
CREATE TABLE IF NOT EXISTS dispatch_requests(id TEXT PRIMARY KEY, conv_id TEXT, booking_ref TEXT, actions TEXT,
    reason TEXT, context TEXT, status TEXT, resolved_by TEXT, note TEXT,
    created_at REAL DEFAULT (strftime('%s','now')), resolved_at REAL);
"""


def create_base_schema(con):
    con.executescript(BASE_SCHEMA)


def seed_base(con):
    c = con.cursor()
    for conc, n in CONCOURSES.items():
        for i in range(1, n + 1):
            c.execute("INSERT OR IGNORE INTO gates VALUES(?,?,?,?)", (f"{conc}{i:02d}", conc, i, i * GATE_SPACING_M))
    if not c.execute("SELECT 1 FROM hub_links LIMIT 1").fetchone():
        c.executemany("INSERT INTO hub_links VALUES(?,?,?)", HUB_LINKS)
    # explicit column list: the v3 migration adds flights.aircraft_reg, so positional inserts would break restarts
    c.executemany("INSERT OR IGNORE INTO flights(flight_no,origin,destination,direction,status,gate,previous_gate,"
                  "sched,est,boarding_close) VALUES(?,?,?,?,?,?,?,?,?,?)", FLIGHTS)
    c.executemany(
        "INSERT OR IGNORE INTO passengers VALUES(?,?,?,?,?,?,?)",
        [(p[0], p[1], p[2], json.dumps(p[3]), p[4], p[5], p[6]) for p in PASSENGERS],
    )
    c.executemany("INSERT OR IGNORE INTO scenarios VALUES(?,?,?,?,?,?)", SCENARIOS)
    con.commit()


def build(reset: bool = True):
    """Create (or, with reset=True, recreate) the synthetic demo database and apply all migrations.
    reset=False upgrades an existing database in place without deleting any data."""
    path = db.DB_PATH
    if reset:
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(path + ext):
                os.remove(path + ext)
    con = connect()
    create_base_schema(con)
    seed_base(con)
    con.close()
    from database.migrations import migrate
    migrate()
    return path


def ensure_database():
    """Used at app start: build if missing, otherwise only run idempotent migrations."""
    if not os.path.exists(db.DB_PATH):
        return build(reset=True)
    return build(reset=False)


if __name__ == "__main__":
    print("Built", build())
