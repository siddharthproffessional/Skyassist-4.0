"""The original ten scenarios (S1–S10) must keep passing, with identical numbers."""
import json
import uuid

import pytest

import tools
from agent import Agent
from approval import get_engine
from db import query
from tests.conftest import wait_for

# Captured from SkyAssist v1 before the 2.0 upgrade (baseline_v1.json).
BASELINE_V1 = {
    "S1": dict(metres=1900, self=68, plan=34, mode="CART", slack=1, decision="ASSIST_AND_HOLD_REQUESTED"),
    "S2": dict(metres=250, self=18, plan=18, mode="SELF", slack=32, decision="SELF_GUIDED"),
    "S3": dict(metres=1150, self=37, plan=23, mode="CART", slack=12, decision="ASSIST_REQUESTED"),
    "S4": dict(metres=400, self=29, plan=25, mode="ESCORT", slack=15, decision="ASSIST_REQUESTED"),
    "S5": dict(metres=800, self=34, plan=20, mode="CART", slack=5, decision="ASSIST_REQUESTED"),
    "S6": dict(metres=2850, self=87, plan=40, mode="CART", slack=-15, decision="MISSED_REBOOK"),
    "S9": dict(metres=1600, self=34, plan=34, mode="SELF", slack=6, decision="SELF_GUIDED"),
    "S10": dict(metres=1450, self=59, plan=32, mode="CART", slack=18, decision="ASSIST_REQUESTED"),
}
SCENARIO_IDS = [f"S{i}" for i in range(1, 11)]


@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_scenario_decision(fresh_db, sid):
    s = query("SELECT * FROM scenarios WHERE id=?", (sid,))[0]
    conv = uuid.uuid4().hex[:8]
    res = Agent(get_engine(), polish=True).handle(conv, s["message"], s["booking_ref"], s["now"])
    assert res["decision"] == s["expected"]
    if res.get("request_id"):
        n = len(query("SELECT 1 FROM messages WHERE conv_id=?", (conv,)))
        assert get_engine().resolve(res["request_id"], True, "TEST-COORD", "")
        assert wait_for(lambda: len(query("SELECT 1 FROM messages WHERE conv_id=?", (conv,))) > n)


@pytest.mark.parametrize("sid", sorted(BASELINE_V1))
def test_numbers_identical_to_v1(fresh_db, sid):
    s = query("SELECT s.now, p.* FROM scenarios s JOIN passengers p USING(booking_ref) WHERE s.id=?", (sid,))[0]
    i, o = tools.get_flight_and_gate_status(s["inbound"]), tools.get_flight_and_gate_status(s["outbound"])
    p = tools.decide_assistance(json.loads(s["needs"]), i["gate"], o["gate"],
                                tools.minutes_until(o["boarding_close"], s["now"]))
    got = dict(metres=p["self"]["metres"], self=p["self"]["total_min"], plan=p["plan"]["total_min"],
               mode=p["plan"]["mode"], slack=p["slack"], decision=p["decision"])
    assert got == BASELINE_V1[sid]
