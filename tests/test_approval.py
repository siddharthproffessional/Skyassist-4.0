"""Approval lifecycle & reliability (acceptance 18–23, 31–33, 35, 36)."""
import asyncio
import threading
import time
import uuid

import pytest

from agent import Agent
from approval import ApprovalEngine, get_engine
from db import query
from services import coordinator_service as cs, passenger_service, request_store
from services.request_store import StateConflict
from tests.conftest import wait_for


def s1_request(pax):
    j = passenger_service.get_journey(pax, "PNR1A2")
    return j["assistance"]["request"]["id"]


def chat_msgs(booking="PNR1A2"):
    return [m["text"] for m in query("SELECT text FROM messages WHERE conv_id=? ORDER BY id", (f"chat-{booking}",))]


def test_18_20_21_approve_records_note_and_resumes_agent(pax, coord):
    rid = s1_request(pax)
    r = cs.decide(coord, rid, True, "Cart #2 at C12", 10)
    assert r["status"] == "APPROVED" and r["resolved_by"] == "Coordinator Sarah" and r["note"] == "Cart #2 at C12"
    assert r["resolved_at_utc"] and r["hold_minutes_approved"] == 10
    ev = [e["event_type"] for e in request_store.events(rid)]
    assert ev[:2] == ["REQUEST_CREATED", "COORDINATOR_NOTIFIED"] and "APPROVED" in ev
    msg = wait_for(lambda: [m for m in chat_msgs() if m.startswith("✅ APPROVED")])
    assert msg and "Staff dispatch is not confirmed yet" in msg[0]
    trace = query("SELECT step FROM trace WHERE conv_id='chat-PNR1A2'")
    assert wait_for(lambda: any("Agent resumed" in t["step"] for t in
                                query("SELECT step FROM trace WHERE conv_id='chat-PNR1A2'")))
    assert trace is not None


def test_19_22_decline_resumes_agent_with_honest_fallback(pax, coord):
    rid = s1_request(pax)
    r = cs.decide(coord, rid, False, "No cart free")
    assert r["status"] == "DECLINED"
    msg = wait_for(lambda: [m for m in chat_msgs() if m.startswith("❌")])
    assert msg and "No staff are on the way" in msg[0] and "Transfer Desk" in msg[0]
    view = passenger_service.get_journey(pax, "PNR1A2")["assistance"]
    assert view["state"] == "DECLINED" and "No staff are on the way" in view["detail"]


def test_23_duplicate_decision_prevented(pax, coord, coord2):
    rid = s1_request(pax)
    cs.decide(coord, rid, True)
    with pytest.raises(StateConflict):
        cs.decide(coord2, rid, False)
    assert request_store.get(rid)["status"] == "APPROVED"
    assert [e["event_type"] for e in request_store.events(rid)].count("APPROVED") == 1


def test_35_concurrent_coordinator_decisions_exactly_one_wins(pax, coord, coord2):
    rid = s1_request(pax)
    results, barrier = [], threading.Barrier(8)

    def worker(i):
        barrier.wait()
        try:
            cs.decide(coord if i % 2 else coord2, rid, bool(i % 2), f"t{i}")
            results.append("ok")
        except StateConflict:
            results.append("conflict")

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("ok") == 1 and results.count("conflict") == 7
    decided = [e for e in request_store.events(rid) if e["event_type"] in ("APPROVED", "DECLINED")]
    assert len(decided) == 1


def test_31_pending_persists_across_reruns_without_duplicates(pax):
    first = s1_request(pax)
    for _ in range(3):  # each Streamlit rerun calls get_journey again
        assert passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"] == first
    assert len(query("SELECT 1 FROM dispatch_requests WHERE booking_ref='PNR1A2'")) == 1
    res = Agent(get_engine()).handle("chat-PNR1A2", "Can I make my connection?", "PNR1A2", "10:00")
    assert res["request_id"] == first and res["created"] is False


def test_32_timeout_never_approves(fresh_db):
    eng = ApprovalEngine(interim_after_s=0.2)
    rid, _ = eng.stage_ex("t", None, ["MOBILITY_CART"], "TEST", {})
    interim = []

    async def waiter():
        try:
            await asyncio.wait_for(eng.wait(rid, lambda r: interim.append(r)), timeout=0.9)
        except asyncio.TimeoutError:
            return "still waiting"

    assert eng.run_continuation(waiter()).result(timeout=3) == "still waiting"
    r = request_store.get(rid)
    assert r["status"] == "PENDING" and r["escalated_at"] and interim
    assert "ESCALATED" in [e["event_type"] for e in request_store.events(rid)]


def test_33_multiple_requests_pending_independently(coord):
    from services.auth_service import authenticate
    ids = []
    for ref in ("PNR1A2", "PNR3C4", "PNR5E6", "PNR0K2"):
        p = authenticate(ref, "demo123", "PASSENGER")
        ids.append(passenger_service.get_journey(p, ref)["assistance"]["request"]["id"])
    assert len(set(ids)) == 4
    assert {r["id"] for r in cs.list_requests(coord, ["PENDING"])} == set(ids)
    cs.decide(coord, ids[1], True)
    assert [request_store.get(i)["status"] for i in ids] == ["PENDING", "APPROVED", "PENDING", "PENDING"]
    assert get_engine().ping_ms() < 200


def test_36_resolved_state_survives_restart(pax, coord):
    rid = s1_request(pax)
    cs.decide(coord, rid, True, "after restart")
    fresh_engine = ApprovalEngine()          # simulates a new process: no in-memory Futures
    d = fresh_engine.run_continuation(fresh_engine.wait(rid)).result(timeout=3)
    assert d["status"] == "APPROVED" and d["note"] == "after restart"
    assert passenger_service.get_journey(pax, "PNR1A2")["assistance"]["state"] == "APPROVED"


def test_decision_without_live_future_still_reaches_passenger(fresh_db, coord):
    rid, _ = request_store.create_request("x", "PNR3C4", ["MOBILITY_CART"], "TEST", {"minutes_left": 30})
    cs.decide(coord, rid, True, "manual")
    notes = request_store.notifications("PNR3C4")
    assert notes[0]["kind"] == "APPROVED"


def test_gate_hold_capped_at_policy_max(pax, coord):
    rid = s1_request(pax)
    with pytest.raises(ValueError):
        cs.decide(coord, rid, True, hold_minutes=15)
    assert request_store.get(rid)["status"] == "PENDING"


def test_dispatch_requires_assignment_and_follows_order(pax, coord):
    rid = s1_request(pax)
    cs.decide(coord, rid, True)
    with pytest.raises(StateConflict):
        cs.advance(coord, rid, "DISPATCHED")
    cs.assign(coord, rid, "ST-03", "CART-02")
    with pytest.raises(StateConflict):
        cs.advance(coord, rid, "EN_ROUTE")
    for st in ("DISPATCHED", "EN_ROUTE", "COMPLETED"):
        cs.advance(coord, rid, st)
    assert query("SELECT status FROM mobility_resources WHERE resource_id='CART-02'")[0]["status"] == "AVAILABLE"


def test_assignment_blocks_double_booking_of_resources(coord):
    from services.auth_service import authenticate
    a = passenger_service.get_journey(authenticate("PNR1A2", "demo123", "PASSENGER"), "PNR1A2")["assistance"]["request"]["id"]
    b = passenger_service.get_journey(authenticate("PNR3C4", "demo123", "PASSENGER"), "PNR3C4")["assistance"]["request"]["id"]
    cs.decide(coord, a, True, staff_id="ST-03", resource_id="CART-01")
    with pytest.raises(StateConflict):
        cs.decide(coord, b, True, resource_id="CART-01")
    assert request_store.get(b)["status"] == "PENDING"   # whole decision rolled back atomically
