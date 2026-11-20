"""Coordinator portal backend (acceptance 14–17) plus KPIs, ordering and filters."""
from services import coordinator_service as cs, passenger_service
from services.auth_service import authenticate


def make_requests():
    out = {}
    for ref in ("PNR1A2", "PNR3C4", "PNR4D5", "PNR0K2"):
        p = authenticate(ref, "demo123", "PASSENGER")
        out[ref] = passenger_service.get_journey(p, ref)["assistance"]["request"]["id"]
    return out


def test_14_15_login_and_pending_queue(coord):
    assert coord.role == "COORDINATOR"
    ids = make_requests()
    q = cs.list_requests(coord, ["PENDING"])
    assert {r["id"] for r in q} == set(ids.values())


def test_queue_ordering_at_risk_first_then_least_time(coord):
    make_requests()
    q = cs.list_requests(coord, ["PENDING"])
    order = [cs.RISK_ORDER[r["risk"]] for r in q]
    assert order == sorted(order)
    at_risk = [r for r in q if r["risk"] == "AT_RISK"]
    assert [r["minutes_left"] for r in at_risk] == sorted(r["minutes_left"] for r in at_risk)
    assert q[0]["booking_ref"] == "PNR1A2"


def test_filters(coord):
    ids = make_requests()
    assert {r["id"] for r in cs.list_requests(coord, None, ["Escort"])} == {ids["PNR4D5"]}
    assert {r["id"] for r in cs.list_requests(coord, None, ["Gate hold"])} == {ids["PNR1A2"]}
    cs.decide(coord, ids["PNR3C4"], False)
    assert {r["id"] for r in cs.list_requests(coord, ["DECLINED"])} == {ids["PNR3C4"]}


def test_16_17_open_request_shows_route_and_calculations(coord):
    ids = make_requests()
    d = cs.request_detail(coord, ids["PNR1A2"])
    r = d["route"]["route"]
    assert r["distance_m"] == 1900 and r["node_path"][-1] == "G_B14" and r["profile"] == "CART"
    assert d["request"]["context_dict"]["self_min"] == 68 and d["request"]["context_dict"]["transfer_min"] == 34
    assert d["summary"] and d["summary_source"].startswith("template")    # deterministic, labelled
    assert d["suggested"]["resources"] and all(x["kind"] in ("CART", "WHEELCHAIR") for x in d["suggested"]["resources"])
    assert [e["event_type"] for e in d["events"]][:2] == ["REQUEST_CREATED", "COORDINATOR_NOTIFIED"]


def test_kpis_are_database_derived(coord):
    k0 = cs.kpis(coord)
    assert k0["pending"] == 0 and k0["active_connections"] == 8
    ids = make_requests()
    cs.decide(coord, ids["PNR3C4"], True)
    k = cs.kpis(coord)
    assert (k["pending"], k["approved"], k["declined"], k["gate_holds"]) == (3, 1, 0, 1)


def test_gate_change_flagged_on_open_request(coord):
    ids = make_requests()
    cs.simulate_gate_change(coord, "SA-218", "B18")
    assert cs.request_detail(coord, ids["PNR1A2"])["gate_changed_since_request"] is True


def test_history_has_timestamps(coord):
    ids = make_requests()
    cs.decide(coord, ids["PNR1A2"], True, "ok")
    h = cs.history(coord)
    assert h and all(e["created_at"] for e in h)
    assert {"REQUEST_CREATED", "COORDINATOR_NOTIFIED", "APPROVED", "PASSENGER_NOTIFIED"} <= {e["event_type"] for e in h}
