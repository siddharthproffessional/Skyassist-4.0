"""U-4.4 — passenger & baggage consistency: seat + bag + delivery note are atomic."""
import pytest

from db import query, query_one, tx
from services.ops import baggage as bg


def snapshot():
    return {
        "seats": query("SELECT * FROM seat_inventory WHERE flight_no IN ('SA-592','SA-594') ORDER BY flight_no, seat_no"),
        "pax": query_one("SELECT outbound FROM passengers WHERE booking_ref='PNRBAG'"),
        "bags": query("SELECT * FROM baggage_items WHERE booking_ref='PNRBAG' ORDER BY bag_tag"),
        "assign": query("SELECT COUNT(*) n FROM bag_flight_assignments WHERE booking_ref='PNRBAG'"),
        "cap": query("SELECT * FROM baggage_capacity ORDER BY flight_no"),
        "notes": query("SELECT COUNT(*) n FROM baggage_delivery_notes"),
        "hist": query("SELECT COUNT(*) n FROM passenger_rebooking_history"),
    }


def test_passenger_can_make_it_but_bag_cannot(ops):
    p = bg.calculate_baggage_feasibility("PNRBAG", "SA-592")
    assert p["passenger_feasible"] is True and p["connection_min"] == 35 and p["min_bag_transfer_min"] == 45
    assert p["same_flight"]["feasible"] is False
    assert p["decision"] == "SEPARATE_FLIGHT" and p["bag_flight"] == "SA-594"


def test_commit_writes_seat_bags_and_delivery_note_together(ops):
    r = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-ok")
    assert r["status"] == "COMMITTED"
    txn = r["txn_id"]
    assert query_one("SELECT 1 x FROM seat_reservations WHERE txn_id=?", (txn,))
    assert query_one("SELECT COUNT(*) n FROM bag_flight_assignments WHERE txn_id=? AND flight_no='SA-594'", (txn,))["n"] == 2
    assert query_one("SELECT 1 x FROM baggage_delivery_notes WHERE txn_id=?", (txn,))
    assert query_one("SELECT 1 x FROM passenger_rebooking_history WHERE txn_id=?", (txn,))
    assert query_one("SELECT 1 x FROM audit_events WHERE txn_id=? AND event_type='REBOOKING_COMMITTED'", (txn,))
    assert query_one("SELECT outbound FROM passengers WHERE booking_ref='PNRBAG'")["outbound"] == "SA-592"


@pytest.mark.parametrize("point", bg.INJECTION_POINTS)
def test_injected_failure_rolls_everything_back(ops, point):
    before = snapshot()
    r = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", f"k-{point}", inject=point)
    assert r["status"] == "ROLLED_BACK" and not r["committed"]
    assert snapshot() == before
    assert query_one("SELECT status FROM rebooking_transactions WHERE txn_id=?", (r["txn_id"],))["status"] == "ROLLED_BACK"


def test_passenger_message_says_bags_travel_separately(ops):
    r = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-msg")
    assert "NOT arrive with you" in r["passenger_message"] and "SA-594" in r["passenger_message"]
    assert query_one("SELECT 1 x FROM notification_events WHERE booking_ref='PNRBAG' AND kind='REBOOKED'")


def test_no_viable_bag_flight_refuses_the_whole_rebooking(ops):
    with tx() as con:
        con.execute("UPDATE baggage_capacity SET used=capacity WHERE flight_no='SA-594'")
    before = snapshot()
    r = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-none")
    assert r["status"] == "REFUSED" and snapshot() == before


def test_idempotent_replay_returns_same_result_without_new_writes(ops):
    a = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-rep")
    n = query_one("SELECT COUNT(*) n FROM seat_reservations")["n"]
    b = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-rep")
    assert b["idempotent_replay"] and b["txn_id"] == a["txn_id"]
    assert query_one("SELECT COUNT(*) n FROM seat_reservations")["n"] == n


def test_second_commit_with_new_key_is_refused_as_duplicate(ops):
    bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-1")
    r = bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-2")
    assert r["status"] in ("ROLLED_BACK", "REFUSED") and not r["committed"]
    assert query_one("SELECT COUNT(*) n FROM seat_reservations WHERE booking_ref='PNRBAG'")["n"] == 1


def test_bag_capacity_never_exceeded(ops):
    bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-cap")
    for c in query("SELECT * FROM baggage_capacity"):
        assert c["used"] <= c["capacity"]


def test_unverified_bag_rule_fails_closed(ops):
    with tx() as con:
        con.execute("UPDATE ops_policies SET verified=0 WHERE policy_key='baggage.min_transfer_min'")
    assert bg.calculate_baggage_feasibility("PNRBAG", "SA-592")["decision"] == "UNKNOWN"
    assert bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-u")["status"] == "REFUSED"


def test_passenger_portal_view_is_truthful(ops):
    assert bg.passenger_baggage_view("PNRBAG")["rebooking"] is None
    bg.commit_rebooking_with_baggage(ops, "PNRBAG", "SA-592", "k-view")
    v = bg.passenger_baggage_view("PNRBAG")
    assert v["separate"] and v["delivery_note"]["carrying_flight"] == "SA-594"
