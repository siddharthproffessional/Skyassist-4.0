"""Navigation engine tests (acceptance 25, 26, 28, 29, 30 and closures/recalculation)."""
import pytest

from services import navigation_service
from services.routing_engine import NoRouteError, RoutingEngine, build_synthetic_graph


def engine():
    return RoutingEngine()


def test_25_shortest_route_c12_to_b14(fresh_db):
    r = engine().shortest_path("C12", "B14", "STEP_FREE")
    assert r.distance_m == 1900
    assert "E_SKY_BC" in r.edge_path and "E_OUTER_AC" not in r.edge_path
    assert r.node_path[0] == "G_C12" and r.node_path[-1] == "G_B14"
    # a walker may use the mezzanine stairs, which is genuinely shorter: 200 + 500 + 550
    walk = engine().shortest_path("C12", "B14", "STANDARD")
    assert walk.distance_m == 1250 and "E_STAIRS_B03_C08" in walk.edge_path


def test_25_shortest_uses_stairs_shortcut_for_walkers(fresh_db):
    r = engine().shortest_path("B03", "C08", "STANDARD")
    assert r.distance_m == 500 and r.edge_path == ["E_STAIRS_B03_C08"]


def test_26_route_distance_equals_sum_of_graph_edges(fresh_db):
    e = engine()
    for a, b, prof in [("C12", "B14", "CART"), ("A06", "C04", "STANDARD"), ("C20", "A15", "STEP_FREE")]:
        r = e.shortest_path(a, b, prof)
        assert r.distance_m == sum(e.edges[x]["distance_m"] for x in r.edge_path)
        assert r.steps[-1].cumulative_m == r.distance_m


def test_26_never_uses_straight_line_distance(fresh_db):
    e = engine()
    a, b = e.nodes["G_C12"], e.nodes["G_B14"]
    straight = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
    assert e.shortest_path("C12", "B14").distance_m != pytest.approx(straight)


def test_directions_are_numbered_and_human_readable(fresh_db):
    r = engine().shortest_path("C12", "B14", "STEP_FREE")
    texts = [s.text for s in r.steps]
    assert [s.index for s in r.steps] == list(range(1, len(r.steps) + 1))
    assert texts[0].startswith("Exit at Gate C12") and texts[-1] == "Arrive at Gate B14."
    assert any("Skywalk B–C" in t for t in texts)


def test_28_gate_change_triggers_recalculation(pax):
    first = navigation_service.current_route("PNR1A2", "G_C12", "B14", "STEP_FREE")
    again = navigation_service.current_route("PNR1A2", "G_C12", "B14", "STEP_FREE")
    assert first["route"]["route_id"] == again["route"]["route_id"] and not again["recalculated"]
    changed = navigation_service.current_route("PNR1A2", "G_C12", "B16", "STEP_FREE")
    assert changed["recalculated"] and "Gate changed from B14 to B16" in changed["reason"]
    assert changed["route"]["distance_m"] == 2000


def test_closed_corridor_reroutes(coord):
    from services import coordinator_service as cs
    cs.set_edge_available(coord, "E_SKY_BC", False, "Maintenance")
    r = engine().shortest_path("C12", "B14", "STEP_FREE")
    assert "E_SKY_BC" not in r.edge_path and "E_OUTER_AC" in r.edge_path
    assert r.distance_m == 600 + 1300 + 500 + 700
    res = navigation_service.current_route("PNR1A2", "G_C12", "B14", "STEP_FREE")
    assert res["route"]["distance_m"] == 3100


def test_29_missing_route_returns_understandable_error(coord):
    from services import coordinator_service as cs
    cs.set_edge_available(coord, "E_SKY_BC", False)
    cs.set_edge_available(coord, "E_OUTER_AC", False)
    with pytest.raises(NoRouteError) as e:
        engine().shortest_path("C12", "B14", "STEP_FREE")
    assert "can be verified" in str(e.value)
    res = navigation_service.current_route("PNR1A2", "G_C12", "B14", "STEP_FREE")
    assert res["route"] is None and res["error"]


def test_30_no_route_fabricated_without_destination(fresh_db):
    with pytest.raises(NoRouteError) as e:
        engine().shortest_path("C12", None)
    assert e.value.reason == "NO_DESTINATION"
    with pytest.raises(NoRouteError):
        engine().shortest_path("C12", "Z99")


def test_engine_is_ui_independent():
    nodes, edges = build_synthetic_graph()
    r = RoutingEngine(nodes, edges).shortest_path("A04", "A09")
    assert r.distance_m == 250
