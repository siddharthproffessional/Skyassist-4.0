"""SYNTHETIC OPERATIONS DEMO DATASET for the five U-4 challenges.

Clearly synthetic. Reuses the authoritative v2 tables (flights, passengers, users) instead of creating
parallel copies, and adds operational data in the v3 tables. `reset_ops_demo()` restores ONLY rows that this
module owns (flights/passengers listed below and the v3 operational tables). v2 passengers, assistance
requests and every audit record are left untouched.
"""
import json

from db import query_one, tx, utcnow
from services.ops.foundation import audit

DEMO_DATE = "2026-11-20"

# flight_no, origin, destination, direction, status, gate, previous_gate, sched, est, boarding_close, aircraft_reg
OPS_FLIGHTS = [
    # U-4.1 disruption: SA-560 cancelled, 40 passengers move to SA-562
    ("SA-550", "LHR", "HUB", "ARRIVAL", "LANDED", "C02", None, "09:55", "10:05", None, None),
    ("SA-560", "HUB", "BOM", "DEPARTURE", "CANCELLED", "C05", None, "11:30", None, None, "A6-SKC"),
    ("SA-562", "HUB", "BOM", "DEPARTURE", "ON_TIME", "C09", None, "14:30", "14:30", "14:15", "A6-SKD"),
    # U-4.4 passenger vs baggage: 35-minute connection, 45-minute minimum bag transfer
    ("SA-590", "CDG", "HUB", "ARRIVAL", "LANDED", "B10", None, "09:55", "10:00", None, None),
    ("SA-591", "HUB", "LHR", "DEPARTURE", "CANCELLED", "B12", None, "11:00", None, None, "A6-SKE"),
    ("SA-592", "HUB", "LHR", "DEPARTURE", "ON_TIME", "B16", None, "10:35", "10:35", "10:20", "A6-SKF"),
    ("SA-594", "HUB", "LHR", "DEPARTURE", "ON_TIME", "B18", None, "12:40", "12:40", "12:25", "A6-SKG"),
    # U-4.2 crew legality
    ("SA-700", "HUB", "MAN", "DEPARTURE", "ON_TIME", "A12", None, "13:00", "13:00", "12:45", "A6-SKA"),
    ("SA-702", "HUB", "OSL", "DEPARTURE", "ON_TIME", "A14", None, "15:00", "15:00", "14:45", "A6-SKH"),
    # U-4.3 maintenance
    ("SA-710", "HUB", "FRA", "DEPARTURE", "ON_TIME", "A16", None, "13:40", "13:40", "13:25", "A6-SKB"),
    # U-4.5 stale approval
    ("EK-812", "HUB", "DXB", "DEPARTURE", "ON_TIME", "C03", None, "12:10", "12:10", "11:55", "A6-EKA"),
    ("SA-880", "HUB", "KWI", "DEPARTURE", "ON_TIME", "A05", None, "12:30", "12:30", "12:15", "A6-SKJ"),
]
FLIGHT_OPS = [
    # flight_no, aircraft_reg, duty_profile_id, required_duty_min, dest_arrival, note
    ("SA-562", "A6-SKD", "DEMO-FDP", 300, "18:05", None),
    ("SA-592", "A6-SKF", "DEMO-FDP", 450, "14:55", None),
    ("SA-594", "A6-SKG", "DEMO-FDP", 450, "16:55", None),
    ("SA-700", "A6-SKA", "DEMO-FDP", 40, "15:10",
     "Proposed operation: push departure; requires 40 min of remaining duty from the operating crew"),
    ("SA-702", "A6-SKH", "UNVERIFIED-OSL", 60, "17:40", "Duty rules for this operation are not verified"),
    ("SA-710", "A6-SKB", "DEMO-FDP", 300, "18:20", None),
    ("EK-812", "A6-EKA", "DEMO-FDP", 120, "13:20", None),
    ("SA-880", "A6-SKJ", "DEMO-FDP", 150, "14:10", None),
]

VULNERABLE = {1: ["WCHR"], 2: ["WCHR", "ELDERLY"], 3: ["ELDERLY"], 4: ["UMNR"], 5: ["ELDERLY"], 6: ["WCHR"]}
SURNAMES = ["Al Mansoori", "Banerjee", "Costa", "Dubois", "Eriksen", "Fernandes", "Ghosh", "Haddad", "Iyer",
            "Jensen", "Khan", "Lopez", "Menon", "Nakamura", "Okafor", "Patel", "Quinn", "Rossi", "Singh",
            "Tanaka", "Usman", "Varga", "Wong", "Xu", "Yilmaz", "Zhou", "Ahmed", "Brown", "Chen", "Das",
            "Evans", "Farah", "Gupta", "Hughes", "Ibrahim", "Joshi", "Kim", "Lee", "Mehra", "Noor"]


def ops_passengers():
    out = []
    for i in range(1, 41):
        needs = VULNERABLE.get(i, [])
        out.append((f"OPS{i:03d}", f"{SURNAMES[i - 1]} ({'vulnerable' if needs else 'general'})", 1,
                    json.dumps(needs), "SA-550", "SA-560", "en"))
    out.append(("PNRBAG", "Rahman family", 2, json.dumps([]), "SA-590", "SA-591", "en"))
    return out


DUTY_PROFILES = [
    ("DEMO-FDP", "SYNTHETIC demo duty profile — not a real regulation", 600, 600,
     "SkyAssist synthetic dataset v3 (labelled demo policy)", 1),
    ("UNVERIFIED-OSL", "Rules for this operation have not been verified", None, None, "not configured", 0),
]
CREW = [  # crew_id, name, role, base, roster_status, availability, elapsed_min, rest_since_min, quals[(type, valid_until)]
    ("C-101", "Capt. Ahmed Rahimi", "CAPTAIN", "HUB", "ACTIVE", "ON_DUTY", 580, 0, [("A350", "2027-06-30")]),
    ("C-102", "FO Maria Lind", "FIRST_OFFICER", "HUB", "ACTIVE", "ON_DUTY", 300, 0, [("A350", "2027-03-31")]),
    ("C-201", "Capt. Omar Farouk", "CAPTAIN", "HUB", "ACTIVE", "ON_DUTY", 200, 0, [("A350", "2027-05-31")]),
    ("C-202", "FO Lena Brandt", "FIRST_OFFICER", "HUB", "ACTIVE", "ON_DUTY", 200, 0, [("A350", "2027-05-31")]),
    ("R-201", "Capt. Imran Khan (reserve)", "CAPTAIN", "HUB", "RESERVE", "AVAILABLE", 0, 900, [("A350", "2026-10-31")]),
    ("R-202", "Capt. Ada Okafor (reserve)", "CAPTAIN", "HUB", "RESERVE", "AVAILABLE", 0, 900, [("B787", "2027-08-31")]),
    ("R-203", "Capt. Erik Lindqvist (reserve)", "CAPTAIN", "HUB", "RESERVE", "AVAILABLE", 0, 840, [("A350", "2027-09-30")]),
    ("R-204", "Capt. Yuki Sato (reserve)", "CAPTAIN", "HUB", "RESERVE", "AVAILABLE", 0, 300, [("A350", "2027-09-30")]),
]
FLIGHT_CREW = [("SA-700", "C-101", "CAPTAIN"), ("SA-700", "C-102", "FIRST_OFFICER"),
               ("SA-702", "C-201", "CAPTAIN"), ("SA-702", "C-202", "FIRST_OFFICER")]
AIRCRAFT = [("A6-SKA", "A350", "IN_SERVICE"), ("A6-SKB", "A350", "IN_SERVICE"), ("A6-SKC", "A350", "IN_SERVICE"),
            ("A6-SKD", "A350", "IN_SERVICE"), ("A6-SKE", "A350", "IN_SERVICE"), ("A6-SKF", "A350", "IN_SERVICE"),
            ("A6-SKG", "A350", "IN_SERVICE"), ("A6-SKH", "A350", "IN_SERVICE"), ("A6-SKJ", "B787", "IN_SERVICE"),
            ("A6-EKA", "B777", "IN_SERVICE")]
DEFECTS = [("DEF-HYD-1", "A6-SKB", "HYDRAULIC", "Green hydraulic system low-pressure warning",
            f"{DEMO_DATE}T08:30:00+00:00", "MAJOR", "OPEN", "NO_DEPARTURE")]
ENGINEERS = [  # id, name, licence, valid_from, valid_to, types, scope, roster
    ("E-501", "Priya Nair", "B1-UAE-45821", "2024-01-01", "2028-01-01", ["A350"], ["HYDRAULIC", "LANDING_GEAR"], "ON_ROSTER"),
    ("E-502", "Tom Becker", "B1-UAE-31007", "2020-01-01", "2026-06-30", ["A350"], ["HYDRAULIC"], "ON_ROSTER"),
    ("E-503", "Lucia Ortiz", "B1-UAE-50112", "2024-01-01", "2028-01-01", ["B787"], ["HYDRAULIC"], "ON_ROSTER"),
    ("E-504", "Ken Mori", "B2-UAE-22019", "2024-01-01", "2028-01-01", ["A350"], ["AVIONICS"], "ON_ROSTER"),
]
EVIDENCE = [("WO-7781", "DEF-HYD-1", "Work order: hydraulic pump inspection, leak check and functional test"),
            ("WO-9001", None, "Unrelated work order (cabin)")]
BAG_CAPACITY = [("SA-562", 80), ("SA-592", 40), ("SA-594", 8)]


def _seat_rows(flight_no, rows, letters="ABCDE"):
    return [(flight_no, f"{r}{c}", "Y", "AVAILABLE", None, 1) for r in rows for c in letters]


def seed_ops_demo(con=None):
    own = con is None
    if own:
        ctx = tx()
        con = ctx.__enter__()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(flights)")]
        has_reg = "aircraft_reg" in cols
        for f in OPS_FLIGHTS:
            if has_reg:
                con.execute("INSERT OR REPLACE INTO flights(flight_no,origin,destination,direction,status,gate,"
                            "previous_gate,sched,est,boarding_close,aircraft_reg) VALUES(?,?,?,?,?,?,?,?,?,?,?)", f)
        con.executemany("INSERT OR REPLACE INTO flight_ops VALUES(?,?,?,?,?,?)", FLIGHT_OPS)
        con.executemany("INSERT OR REPLACE INTO passengers VALUES(?,?,?,?,?,?,?)", ops_passengers())
        con.execute("INSERT OR IGNORE INTO scenarios VALUES('U44','Passenger makes it, bag does not','PNRBAG',"
                    "'10:00','Our flight was cancelled, can we get to London?','REBOOK')")
        # seats: SA-562 has 45 free seats (rows 10-18); SA-592/594 have a few
        con.executemany("INSERT OR REPLACE INTO seat_inventory VALUES(?,?,?,?,?,?)",
                        _seat_rows("SA-562", range(10, 19)) + _seat_rows("SA-592", range(30, 32))
                        + _seat_rows("SA-594", range(40, 42)))
        for fl, cap in BAG_CAPACITY:
            con.execute("INSERT OR REPLACE INTO baggage_capacity VALUES(?,?,0,1)", (fl, cap))
        bags = [(f"BAG-OPS{i:03d}", f"OPS{i:03d}", 21.0, "HUB transfer sortation", "IN_TRANSFER", "SA-550")
                for i in range(1, 41)]
        bags += [("BAG-RAH-1", "PNRBAG", 23.0, "HUB transfer sortation", "IN_TRANSFER", "SA-590"),
                 ("BAG-RAH-2", "PNRBAG", 19.5, "HUB transfer sortation", "IN_TRANSFER", "SA-590")]
        con.executemany("INSERT OR REPLACE INTO baggage_items VALUES(?,?,?,?,?,?)", bags)
        for p in DUTY_PROFILES:
            con.execute("INSERT OR IGNORE INTO duty_rule_profiles VALUES(?,?,?,?,?,?)", p)
        for c in CREW:
            con.execute("INSERT OR REPLACE INTO crew_members VALUES(?,?,?,?,?,?)", c[:6])
            con.execute("INSERT OR REPLACE INTO crew_duty_records VALUES(?,?,?,?,?,?)",
                        (c[0], "DEMO-FDP", c[6], c[7], "SYNTHETIC roster feed", utcnow()))
            for t, until in c[8]:
                con.execute("INSERT OR REPLACE INTO crew_qualifications VALUES(?,?,?,?)",
                            (c[0], t, f"LIC-{c[0]}", until))
        for f, cid, role in FLIGHT_CREW:
            con.execute("INSERT OR REPLACE INTO flight_crew VALUES(?,?,?,'ASSIGNED',?)", (f, cid, role, utcnow()))
        con.executemany("INSERT OR REPLACE INTO aircraft VALUES(?,?,?)", AIRCRAFT)
        for d in DEFECTS:
            con.execute("INSERT OR REPLACE INTO aircraft_defects VALUES(?,?,?,?,?,?,?,?,NULL,NULL)", d)
        for e in ENGINEERS:
            con.execute("INSERT OR REPLACE INTO maintenance_engineers VALUES(?,?,?,?,?,?,?,?)",
                        (*e[:5], json.dumps(e[5]), json.dumps(e[6]), e[7]))
        for ev in EVIDENCE:
            con.execute("INSERT OR REPLACE INTO maintenance_evidence VALUES(?,?,?,?)", (*ev, utcnow()))
        con.execute("INSERT OR IGNORE INTO departure_holds(flight_no,hold_type,reason,status,created_at) "
                    "VALUES('SA-710','MAINTENANCE','Open defect DEF-HYD-1 (NO_DEPARTURE restriction)','ACTIVE',?)",
                    (utcnow(),))
        _seed_ops_users(con)
        audit(con, "system", "SIMULATOR", "DEMO_DATA_SEEDED", "dataset", "ops-demo-v3",
              reason="Synthetic operations demo data loaded")
    except Exception:
        if own:
            ctx.__exit__(*__import__("sys").exc_info())
        raise
    else:
        if own:
            ctx.__exit__(None, None, None)


def _seed_ops_users(con):
    import os
    from services.auth_service import hash_password
    pw = os.getenv("PASSENGER_DEMO_PASSWORD", "demo123")
    for ref, name in (("PNRBAG", "Rahman family"), ("OPS001", "Al Mansoori (vulnerable)"),
                      ("OPS020", "Tanaka (general)")):
        if not con.execute("SELECT 1 FROM users WHERE username=?", (ref,)).fetchone():
            h, salt = hash_password(pw)
            con.execute("INSERT INTO users VALUES(?,?,?,?,?,?,1,?)", (ref, "PASSENGER", name, h, salt, ref, utcnow()))


OPS_TABLES_RESET = [
    "seat_reservations", "rebooking_jobs", "rebooking_batches", "rebooking_batch_items", "rebooking_transactions",
    "passenger_rebooking_history", "bag_flight_assignments", "baggage_delivery_notes", "crew_messages",
    "crew_assignment_proposals", "approval_requests", "approval_decisions", "operational_actions",
    "maintenance_validation_events", "operational_alerts", "workflow_outbox", "idempotency_records",
    "seat_inventory", "baggage_capacity", "baggage_items", "flight_crew", "crew_duty_records",
    "crew_qualifications", "crew_members", "aircraft_defects", "maintenance_engineers", "maintenance_evidence",
    "aircraft", "flight_ops", "departure_holds",
]


def reset_ops_demo(actor="system"):
    """SYNTHETIC DEMO RESET. Restores only the operations demo dataset. v2 data and audit history are kept.
    Maintenance sign-offs are immutable records and are never deleted; they are re-validated against the
    fresh dataset only when new ones are submitted."""
    from services.auth_service import PermissionDenied  # noqa: F401
    with tx() as con:
        for t in OPS_TABLES_RESET:
            con.execute(f"DELETE FROM {t}")
        con.execute("DELETE FROM resource_versions WHERE resource_id LIKE 'GATE:%' OR resource_id LIKE 'FLIGHT:%'")
        # new dataset generation: earlier immutable sign-offs stay on record but belong to the old generation
        con.execute("UPDATE ops_policies SET value=CAST(value AS INTEGER)+1, updated_at=? WHERE policy_key='demo.epoch'",
                    (utcnow(),))
        seed_ops_demo(con)
        audit(con, actor, "SIMULATOR", "DEMO_RESET", "dataset", "ops-demo-v3",
              reason="Synthetic demo reset (operations data only)")


def is_seeded():
    return query_one("SELECT 1 AS x FROM flights WHERE flight_no='SA-562'") is not None


def ensure_seeded():
    if not is_seeded():
        seed_ops_demo()
