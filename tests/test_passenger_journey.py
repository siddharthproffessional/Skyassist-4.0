"""Passenger portal backend (acceptance 1–7, 10–13) and chat intents."""
from agent import Agent
from approval import get_engine
from db import query
from services import coordinator_service as cs, navigation_service, passenger_service
from services.auth_service import authenticate


def test_01_02_03_login_own_flight_correct_gate(pax):
    assert pax.role == "PASSENGER" and pax.booking_ref == "PNR1A2"
    j = passenger_service.get_journey(pax, "PNR1A2")
    assert j["inbound"]["flight_no"] == "DXB-402" and j["outbound"]["flight_no"] == "SA-218"
    assert j["dest_gate"] == "B14" and j["gate_changed_from"] == "B07"
    assert "departs from Gate B14" in j["messages"][0]


def test_03_outdated_gate_never_used(fresh_db):
    p = authenticate("PNR9J1", "demo123", "PASSENGER")
    j = passenger_service.get_journey(p, "PNR9J1")
    assert j["dest_gate"] == "C04" and j["route_result"]["route"]["dest_gate"] == "C04"


def test_04_05_valid_route_with_numbered_directions(pax):
    rr = passenger_service.get_journey(pax, "PNR1A2")["route_result"]
    r = rr["route"]
    assert r["distance_m"] == 1900 and r["node_path"][0] == "G_C12" and r["node_path"][-1] == "G_B14"
    assert [s["index"] for s in r["steps"]] == list(range(1, len(r["steps"]) + 1))
    assert rr["location"]["live"] is False and rr["location"]["source"] == "ARRIVAL_GATE"


def test_06_progress_advances_and_persists(pax):
    j = passenger_service.get_journey(pax, "PNR1A2")
    n = len(j["route_result"]["route"]["steps"])
    navigation_service.start("PNR1A2")
    assert navigation_service.move("PNR1A2", 1, n) == 1
    assert navigation_service.move("PNR1A2", 1, n) == 2
    assert navigation_service.move("PNR1A2", -1, n) == 1
    assert passenger_service.get_journey(pax, "PNR1A2")["route_result"]["progress"]["step_index"] == 1


def test_07_gate_change_updates_directions(pax, coord):
    before = passenger_service.get_journey(pax, "PNR1A2")["route_result"]["route"]
    cs.simulate_gate_change(coord, "SA-218", "B18")
    j = passenger_service.get_journey(pax, "PNR1A2")
    after = j["route_result"]
    assert j["dest_gate"] == "B18" and after["recalculated"] and "B14 to B18" in after["reason"]
    assert after["route"]["steps"][-1]["text"] == "Arrive at Gate B18." and before["distance_m"] != after["route"]["distance_m"]
    assert any(n["kind"] == "GATE_CHANGE" for n in query("SELECT kind FROM notification_events WHERE booking_ref='PNR1A2'"))


def test_manual_location_update_recalculates(pax):
    from services.location_provider import ManualLocationProvider
    passenger_service.get_journey(pax, "PNR1A2")
    ManualLocationProvider.set_manual("PNR1A2", "HUB_C")
    rr = passenger_service.get_journey(pax, "PNR1A2")["route_result"]
    assert rr["location"]["source"] == "MANUAL" and rr["route"]["distance_m"] == 1300 and rr["recalculated"]


def test_10_pending_status_visible(pax):
    v = passenger_service.get_journey(pax, "PNR1A2")["assistance"]
    assert v["state"] == "PENDING COORDINATOR APPROVAL"
    assert "not been confirmed" in v["detail"] and "No staff dispatch has been confirmed" in v["detail"]


def test_11_approved_status_after_decision(pax, coord):
    rid = passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"]
    cs.decide(coord, rid, True, "See you at C12", 10)
    j = passenger_service.get_journey(pax, "PNR1A2")
    assert j["assistance"]["state"] == "APPROVED" and "Coordinator Sarah" in j["assistance"]["detail"]
    assert j["risk"] == "TIGHT"   # assisted plan only counts once approved


def test_12_declined_status_after_rejection(pax, coord):
    rid = passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"]
    cs.decide(coord, rid, False, "No cart")
    j = passenger_service.get_journey(pax, "PNR1A2")
    assert j["assistance"]["state"] == "DECLINED" and j["risk"] == "AT_RISK"


def test_13_never_false_dispatch(pax, coord):
    rid = passenger_service.get_journey(pax, "PNR1A2")["assistance"]["request"]["id"]
    cs.decide(coord, rid, True)
    v = passenger_service.get_journey(pax, "PNR1A2")["assistance"]
    assert v["state"] == "APPROVED" and "not been assigned or dispatched" in v["detail"]
    assert "on their way" not in v["detail"] and "dispatched to you" not in v["detail"]
    cs.assign(coord, rid, "ST-03", "CART-02")
    assert passenger_service.get_journey(pax, "PNR1A2")["assistance"]["state"] == "APPROVED"
    cs.advance(coord, rid, "DISPATCHED")
    assert passenger_service.get_journey(pax, "PNR1A2")["assistance"]["state"] == "DISPATCHED"


def test_risk_messages_come_from_backend_numbers(pax):
    j = passenger_service.get_journey(pax, "PNR1A2")
    assert j["minutes_left"] == 35 and j["plan"]["self"]["total_min"] == 68 and j["plan"]["plan"]["total_min"] == 34
    assert "You have 35 minutes" in j["messages"][1] and "68 minutes on your own, 34 minutes" in j["messages"][2]


def test_cancelled_connection_routes_to_transfer_desk(fresh_db):
    p = authenticate("PNR7G8", "demo123", "PASSENGER")
    j = passenger_service.get_journey(p, "PNR7G8")
    assert j["state"] == "CANCELLED" and j["route_result"]["route"]["node_path"][-1] == "TD_B"


def test_unknown_connection_no_guessed_gate(fresh_db):
    p = authenticate("PNR8H9", "demo123", "PASSENGER")
    j = passenger_service.get_journey(p, "PNR8H9")
    assert j["state"] == "NO_CONNECTION" and "route_result" not in j


def test_passenger_can_request_help_manually(fresh_db):
    from services import assistance_service
    p = authenticate("PNR2B3", "demo123", "PASSENGER")
    j = passenger_service.get_journey(p, "PNR2B3")
    assert j["assistance"]["request"] is None
    rid, created = assistance_service.passenger_request(p, "PNR2B3", ["STAFF_ESCORT"], "First time here", j)
    assert created and passenger_service.get_journey(p, "PNR2B3")["assistance"]["request"]["id"] == rid


def test_chat_status_and_desk_intents_use_backend(pax, coord):
    agent = Agent(get_engine())
    passenger_service.get_journey(pax, "PNR1A2")
    assert agent.handle("chat-PNR1A2", "Has my assistance been approved?", "PNR1A2")["decision"] == "STATUS"
    last = query("SELECT text FROM messages WHERE conv_id='chat-PNR1A2' ORDER BY id DESC LIMIT 1")[0]["text"]
    assert "PENDING" in last and "NOT confirmed" in last
    assert agent.handle("chat-PNR1A2", "Where is the nearest assistance desk?", "PNR1A2")["decision"] == "DESK"
    last = query("SELECT text FROM messages WHERE conv_id='chat-PNR1A2' ORDER BY id DESC LIMIT 1")[0]["text"]
    assert "620 m from gate C12" in last
