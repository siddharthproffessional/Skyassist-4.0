"""Accessibility routing (acceptance 8 and 27)."""
import pytest

from services import passenger_service
from services.auth_service import authenticate
from services.routing_engine import NoRouteError, RoutingEngine, profile_for


def test_27_step_free_avoids_stairs_and_escalators(fresh_db):
    e = RoutingEngine()
    r = e.shortest_path("B03", "C08", "STEP_FREE")
    used = [e.edges[x] for x in r.edge_path]
    assert r.distance_m == 1150
    assert not any(int(x["stairs"]) or int(x["escalator"]) for x in used)
    assert sum(int(x["elevator"]) for x in used) == 2


def test_walkers_take_escalator_wheelchairs_take_lift(fresh_db):
    e = RoutingEngine()
    std = e.shortest_path("C02", "B02", "STANDARD")
    sf = e.shortest_path("C02", "B02", "STEP_FREE")
    assert "E_ESC_C" in std.edge_path and "E_ELV_C" in sf.edge_path
    assert std.distance_m == sf.distance_m
    assert any("step-free lift" in s.text for s in sf.steps)


def test_profiles_from_needs():
    assert profile_for(["WCHR"]) == "STEP_FREE"
    assert profile_for(["STROLLER"]) == "STEP_FREE"
    assert profile_for(["ELDERLY"]) == "STEP_FREE"
    assert profile_for([]) == "STANDARD"
    assert profile_for(["WCHR"], "CART") == "CART"


def test_08_wheelchair_passenger_gets_verified_accessible_route(pax):
    j = passenger_service.get_journey(pax, "PNR1A2")
    rr = j["route_result"]
    assert rr["profile"] == "STEP_FREE" and rr["route"]["accessible_verified"]
    e = RoutingEngine()
    assert all(int(e.edges[x]["accessible"]) for x in rr["route"]["edge_path"])


def test_no_silent_fallback_to_inaccessible_route(coord):
    from services import coordinator_service as cs
    cs.set_edge_available(coord, "E_ELV_C", False, "Lift out of service")
    e = RoutingEngine()
    walk = e.shortest_path("C12", "B14", "STANDARD")             # walkers still have a route
    assert walk.distance_m == 1250 and not any(int(e.edges[x]["elevator"]) for x in walk.edge_path)
    with pytest.raises(NoRouteError):
        e.shortest_path("C12", "B14", "STEP_FREE")
    pax = authenticate("PNR1A2", "demo123", "PASSENGER")
    j = passenger_service.get_journey(pax, "PNR1A2")
    assert j["state"] == "NO_ROUTE" and j["route_result"]["route"] is None


def test_ui_navigation_survives_lift_closure(coord):
    """Regression (found while filming the demo): the navigation tab crashed when no step-free route existed."""
    import os
    from streamlit.testing.v1 import AppTest
    from services import coordinator_service as cs
    cs.set_edge_available(coord, "E_ELV_C", False, "Lift out of service")
    pax = authenticate("PNR1A2", "demo123", "PASSENGER")
    rr = passenger_service.get_journey(pax, "PNR1A2")["route_result"]
    assert rr["location"]["node_id"] == "G_C12" and rr["route"] is None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    at = AppTest.from_file(os.path.join(root, "views", "passenger.py"), default_timeout=30)
    at.session_state["principals"] = {"PASSENGER": pax}
    at.run()
    assert not at.exception
    assert any("step-free" in e.value for e in at.error)
