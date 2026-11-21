"""SkyAssist 4.0 — DIGITAL TWIN READ MODELS (read-only).

The browser renders exactly what these functions return; it never computes crew legality, seat availability,
baggage feasibility, maintenance clearance or approval validity itself.

Geometry: the terminal graph (terminal_nodes / terminal_edges) is the SkyAssist synthetic dataset. Its x/y values
and the 3D placement derived from them are ILLUSTRATIVE; walking distances always come from edge lengths.
"""
import hashlib
import json

from db import query, query_one
from services.ops import maintenance
from services.ops.foundation import policy

DATA_LABEL = ("SYNTHETIC DEMO DATA — illustrative terminal geometry; distances from the SkyAssist routing graph; "
              "no live airport, aircraft or passenger tracking.")
GATE_STATES = ["AVAILABLE", "OCCUPIED", "BOARDING", "DEPARTING", "BLOCKED", "UNDER_REVIEW", "PENDING_APPROVAL"]


def _j(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def layout():
    nodes = query("SELECT node_id, name, node_type, concourse, floor, x, y FROM terminal_nodes ORDER BY node_id")
    edges = query("SELECT edge_id, from_node, to_node, distance_m, accessible, stairs, escalator, elevator, cart_ok, "
                  "kind, direction_description, geometry, available, closure_reason FROM terminal_edges")
    for e in edges:
        e["geometry"] = _j(e["geometry"])
    gates = query("SELECT gate, concourse, number, metres_from_hub FROM gates ORDER BY gate")
    return {"nodes": nodes, "edges": edges, "gates": gates, "coordinates": "ILLUSTRATIVE", "label": DATA_LABEL}


def state_version():
    """Cheap change detector for the live event stream: any audit event or edge change changes it."""
    a = query_one("SELECT MAX(event_id) m FROM audit_events")["m"] or 0
    b = query_one("SELECT COALESCE(MAX(id),0) m FROM audit_log")["m"] or 0
    c = query_one("SELECT COALESCE(MAX(step_id),0) m FROM agent_steps")["m"] or 0
    d = query_one("SELECT COALESCE(MAX(id),0) m FROM request_events")["m"] or 0
    e = query_one("SELECT GROUP_CONCAT(edge_id) s FROM terminal_edges WHERE available=0")["s"] or ""
    return hashlib.sha1(f"{a}|{b}|{c}|{d}|{e}".encode()).hexdigest()[:12]


def _holds():
    out = {}
    for h in query("SELECT * FROM departure_holds WHERE status='ACTIVE'"):
        out.setdefault(h["flight_no"], []).append({"type": h["hold_type"], "reason": h["reason"]})
    return out


def _flight_health(f, holds, pending_flights, alerts_by_entity):
    reasons = []
    if f["status"] == "CANCELLED":
        level = "critical"
        reasons.append("Cancelled")
    elif f["flight_no"] in holds:
        level = "critical"
        reasons += [f"Departure blocked — {h['type'].lower()}" for h in holds[f["flight_no"]]]
    elif f["flight_no"] in pending_flights:
        level = "warning"
        reasons.append("Decision pending")
    elif f["status"] in ("DELAYED", "GATE_CHANGED"):
        level = "warning"
        reasons.append(f["status"].replace("_", " ").title())
    else:
        level = "normal"
    if alerts_by_entity.get(f["flight_no"]):
        reasons.append(f"{alerts_by_entity[f['flight_no']]} open alert(s)")
    return level, reasons


def flights_state():
    holds = _holds()
    pending = {r["flight_no"] for r in query("SELECT flight_no FROM approval_requests WHERE status IN "
                                             "('PENDING','APPROVED')")}
    pending |= {r["flight_no"] for r in query("SELECT flight_no FROM journey_approvals WHERE status='PENDING'")}
    pending |= {r["flight_no"] for r in query("SELECT flight_no FROM crew_assignment_proposals WHERE "
                                              "status='PENDING_APPROVAL'")}
    alerts = {r["entity_id"]: r["n"] for r in query("SELECT entity_id, COUNT(*) n FROM operational_alerts WHERE "
                                                    "status='OPEN' GROUP BY entity_id")}
    pax = {r["outbound"]: r["n"] for r in query("SELECT outbound, COUNT(*) n FROM passengers GROUP BY outbound")}
    inb = {r["inbound"]: r["n"] for r in query("SELECT inbound, COUNT(*) n FROM passengers GROUP BY inbound")}
    cols = [c["name"] for c in query("PRAGMA table_info(flights)")]
    sel = "flight_no, origin, destination, direction, status, gate, previous_gate, sched, est, boarding_close" + \
          (", aircraft_reg" if "aircraft_reg" in cols else "")
    out = []
    for f in query(f"SELECT {sel} FROM flights ORDER BY COALESCE(est, sched), flight_no"):
        level, reasons = _flight_health(f, holds, pending, alerts)
        f.update(health=level, reasons=reasons, holds=holds.get(f["flight_no"], []),
                 passengers=pax.get(f["flight_no"], 0) if f["direction"] == "DEPARTURE" else inb.get(f["flight_no"], 0))
        out.append(f)
    return out


def gates_state(flights=None):
    flights = flights if flights is not None else flights_state()
    by_gate = {}
    for f in flights:
        if f["gate"]:
            by_gate.setdefault(f["gate"], []).append(f)
    pending = {}
    for a in query("SELECT approval_id, flight_no, target_resource AS resource_id, status FROM approval_requests WHERE status IN "
                   "('PENDING','APPROVED')"):
        pending.setdefault(a["resource_id"].removeprefix("GATE:"), []).append(a)
    stale = {}
    for a in query("SELECT approval_id, flight_no, target_resource AS resource_id, stale_reason FROM approval_requests WHERE "
                   "status='STALE'"):
        stale.setdefault(a["resource_id"].removeprefix("GATE:"), []).append(a)
    versions = {r["resource_id"].removeprefix("GATE:"): r["version"] for r in
                query("SELECT resource_id, version FROM resource_versions WHERE resource_id LIKE 'GATE:%'")}
    changed_from = {}
    for f in flights:
        if f["status"] == "GATE_CHANGED" and f["previous_gate"]:
            changed_from.setdefault(f["previous_gate"], []).append(f["flight_no"])
    out = []
    for g in query("SELECT gate, concourse, number FROM gates ORDER BY gate"):
        gid = g["gate"]
        fl = by_gate.get(gid, [])
        deps = [f for f in fl if f["direction"] == "DEPARTURE" and f["status"] != "CANCELLED"]
        arrs = [f for f in fl if f["direction"] == "ARRIVAL"]
        cancelled = [f for f in fl if f["status"] == "CANCELLED"]
        if any(f["holds"] for f in deps):
            st = "BLOCKED"
        elif gid in pending:
            st = "PENDING_APPROVAL"
        elif gid in stale or any(f["health"] == "warning" and "Decision pending" in f["reasons"] for f in deps):
            st = "UNDER_REVIEW"
        elif any(f["status"] == "BOARDING" for f in deps):
            st = "BOARDING"
        elif any(f["status"] in ("DEPARTED", "DEPARTING", "PUSHBACK") for f in deps):
            st = "DEPARTING"
        elif deps or arrs:
            st = "OCCUPIED"
        else:
            st = "AVAILABLE"
        out.append({"gate": gid, "concourse": g["concourse"], "number": g["number"], "status": st,
                    "departures": [f["flight_no"] for f in deps], "arrivals": [f["flight_no"] for f in arrs],
                    "cancelled": [f["flight_no"] for f in cancelled], "pending_approvals": pending.get(gid, []),
                    "stale_approvals": stale.get(gid, []), "version": versions.get(gid, 1),
                    "gate_changed_away": changed_from.get(gid, []),
                    "affected": bool(cancelled or changed_from.get(gid) or gid in stale)})
    return out


def kpis(flights):
    pend_gate = query_one("SELECT COUNT(*) n FROM approval_requests WHERE status IN ('PENDING','APPROVED')")["n"]
    pend_j = query_one("SELECT COUNT(*) n FROM journey_approvals WHERE status='PENDING'")["n"]
    pend_c = query_one("SELECT COUNT(*) n FROM crew_assignment_proposals WHERE status='PENDING_APPROVAL'")["n"]
    pend_a = query_one("SELECT COUNT(*) n FROM dispatch_requests WHERE status='PENDING'")["n"]
    esc = query_one("SELECT COUNT(*) n FROM rebooking_batches WHERE status='ESCALATED'")["n"]
    affected = sum(f["passengers"] for f in flights if f["direction"] == "DEPARTURE" and
                   (f["status"] == "CANCELLED" or f["holds"]))
    return {
        "active_flights": sum(f["status"] != "CANCELLED" for f in flights),
        "disrupted_flights": sum(f["health"] == "critical" for f in flights),
        "affected_passengers": affected,
        "pending_approvals": pend_gate + pend_j + pend_c + pend_a + esc,
        "pending_breakdown": {"gate": pend_gate, "journey": pend_j, "crew": pend_c, "assistance": pend_a,
                              "escalated_batches": esc},
        "rebooked_passengers": query_one("SELECT COUNT(*) n FROM passenger_rebooking_history")["n"],
        "successful_recoveries": query_one("SELECT COUNT(*) n FROM rebooking_transactions WHERE status='COMMITTED'")["n"],
        "failed_transactions": query_one("SELECT COUNT(*) n FROM rebooking_transactions WHERE status='ROLLED_BACK'")["n"],
        "open_alerts": query_one("SELECT COUNT(*) n FROM operational_alerts WHERE status='OPEN'")["n"],
        "closed_corridors": query_one("SELECT COUNT(*) n FROM terminal_edges WHERE available=0")["n"],
    }


def alerts_feed(limit=40):
    rows = query("SELECT alert_id, module, severity, entity_id, title, detail, status, created_at FROM "
                 "operational_alerts WHERE status='OPEN' ORDER BY alert_id DESC LIMIT ?", (limit,))
    return rows


def recent_events(limit=12):
    return query("SELECT event_id, occurred_at, actor, module, event_type, entity_id, result, reason FROM audit_events "
                 "ORDER BY event_id DESC LIMIT ?", (limit,))


def system_health():
    from services.ai import gateway
    from services.ops import outbox
    chain = gateway.configured_chain()
    last = {r["provider"]: r for r in query("SELECT provider, outcome, created_at FROM llm_calls WHERE id IN "
                                            "(SELECT MAX(id) FROM llm_calls GROUP BY provider)")}
    providers = []
    for p in ("gemini", "groq"):
        conf = p in chain
        l = last.get(p)
        if not conf:
            st = "NOT_CONFIGURED"
        elif gateway.breaker_state().get(p, {}).get("open"):
            st = "CIRCUIT_OPEN"
        elif l and l["outcome"] == "OK":
            st = "HEALTHY"
        elif l:
            st = "DEGRADED"
        else:
            st = "CONFIGURED_UNVERIFIED"
        providers.append({"provider": p, "status": st, "last_outcome": l["outcome"] if l else None,
                          "last_at": l["created_at"] if l else None})
    return {"providers": providers, "rules_fallback": "ALWAYS_AVAILABLE", "n8n_mode": outbox.mode(),
            "outbox": outbox.stats()}


def twin_state():
    flights = flights_state()
    gates = gates_state(flights)
    closed = query("SELECT edge_id, from_node, to_node, closure_reason FROM terminal_edges WHERE available=0")
    from services.agents.runtime import agent_statuses
    return {"version": state_version(), "label": DATA_LABEL, "epoch": int(policy("demo.epoch", "1")),
            "flights": flights, "gates": gates, "closed_edges": closed, "kpis": kpis(flights),
            "alerts": alerts_feed(), "agents": agent_statuses(), "events": recent_events(), "health": system_health()}


# ------------------------------------------------------------------ entity detail panels
def flight_profile(flight_no):
    from services.ops import baggage, crew
    flights = {f["flight_no"]: f for f in flights_state()}
    f = flights.get(flight_no)
    if not f:
        return None
    if f["direction"] == "DEPARTURE":
        pax = query("SELECT booking_ref, lead_name, party_size, needs, inbound FROM passengers WHERE outbound=? ORDER BY "
                    "booking_ref", (flight_no,))
    else:
        pax = query("SELECT booking_ref, lead_name, party_size, needs, outbound FROM passengers WHERE inbound=? ORDER BY "
                    "booking_ref", (flight_no,))
    for p in pax:
        p["needs"] = _j(p["needs"], [])
    moved_in = query("SELECT booking_ref, from_flight, seat_no, created_at FROM passenger_rebooking_history WHERE "
                     "to_flight=? ORDER BY id", (flight_no,))
    moved_out = query("SELECT booking_ref, to_flight, seat_no FROM passenger_rebooking_history WHERE from_flight=? "
                      "ORDER BY id", (flight_no,))
    bags = query("SELECT a.bag_tag, a.booking_ref, a.kind, b.status, b.origin_flight AS inbound_flight FROM bag_flight_assignments a "
                 "LEFT JOIN baggage_items b USING(bag_tag) WHERE a.flight_no=? AND a.status='ACTIVE'", (flight_no,))
    cap = query_one("SELECT * FROM baggage_capacity WHERE flight_no=?", (flight_no,))
    crew_rows = crew.crew_board(flight_no)
    has_ops = query_one("SELECT 1 x FROM flight_ops WHERE flight_no=?", (flight_no,)) is not None
    dep = maintenance.departure_status(flight_no) if has_ops else None
    defects = query("SELECT * FROM aircraft_defects WHERE reg=?", (f.get("aircraft_reg"),)) if f.get("aircraft_reg") \
        else []
    signoffs = []
    for d in defects:
        for s in maintenance.signoffs(d["defect_id"]):
            s["reasons_list"] = _j(s.get("reasons"), [])
            signoffs.append(s)
    approvals = query("SELECT approval_id, action_type, target_resource AS resource_id, status, requested_at, expires_at, stale_reason "
                      "FROM approval_requests WHERE flight_no=? ORDER BY requested_at DESC", (flight_no,))
    japprovals = query("SELECT approval_id, action, booking_ref, status, risk_reason, expires_at FROM journey_approvals "
                       "WHERE flight_no=? ORDER BY created_at DESC", (flight_no,))
    proposals = crew.proposals(flight_no)
    jobs = query("SELECT job_id, status, total, vulnerable FROM rebooking_jobs WHERE disrupted_flight=? OR "
                 "target_flight=? ORDER BY created_at DESC", (flight_no, flight_no))
    seats = query_one("SELECT SUM(status='AVAILABLE') free, COUNT(*) total FROM seat_inventory WHERE flight_no=?",
                      (flight_no,))
    vuln = {"WCHR", "UMNR", "ELDERLY"}
    return {"flight": f, "passengers": pax, "passenger_count": len(pax),
            "vulnerable_count": sum(bool(set(p["needs"]) & vuln) for p in pax),
            "rebooked_in": moved_in, "rebooked_out": moved_out, "bags": bags, "bag_capacity": cap,
            "crew": [{k: c.get(k) for k in ("crew_id", "name", "role", "status")} |
                     {"verdict": (c.get("validation") or {}).get("verdict"),
                      "remaining_min": (c.get("validation") or {}).get("remaining_min"),
                      "required_min": (c.get("validation") or {}).get("required_min")} for c in crew_rows],
            "departure": dep, "defects": defects, "signoffs": signoffs, "gate_approvals": approvals,
            "journey_approvals": japprovals, "crew_proposals": proposals, "rebooking_jobs": jobs,
            "seats": seats if seats and seats["total"] else None,
            "baggage_detail": {b: baggage.passenger_baggage_view(b) for b in
                               {x["booking_ref"] for x in bags if x["kind"] == "SEPARATE"}},
            "label": DATA_LABEL}


def gate_detail(gate):
    gates = {g["gate"]: g for g in gates_state()}
    g = gates.get(gate)
    if not g:
        return None
    hist = query("SELECT event_id, occurred_at, actor, event_type, entity_id, old_state, new_state, result FROM "
                 "audit_events WHERE module='GATES' AND (old_state LIKE ? OR new_state LIKE ? OR entity_id IN "
                 "(SELECT approval_id FROM approval_requests WHERE target_resource=?)) ORDER BY event_id DESC LIMIT 20",
                 (f'%"{gate}"%', f'%"{gate}"%', f"GATE:{gate}"))
    node = query_one("SELECT * FROM terminal_nodes WHERE node_id=?", (f"G_{gate}",))
    return {**g, "node": node, "history": hist, "conflicts": [a for a in g["stale_approvals"]],
            "label": DATA_LABEL}


# ------------------------------------------------------------------ routes & baggage paths for the 3D layers
def _route(engine, a, b, profile):
    from services.routing_engine import NoRouteError
    try:
        r = engine.shortest_path(a, b, profile)
        return {"from": a, "to": b, "profile": profile, "distance_m": r.distance_m, "node_path": r.node_path,
                "edge_path": r.edge_path, "walk_min": round(r.distance_m / 80, 1),
                "steps": [s.text for s in r.steps], "ok": True}
    except NoRouteError as e:
        return {"from": a, "to": b, "profile": profile, "ok": False, "reason": str(e)}


def connection_routes(flight_no=None, limit=24):
    """Passenger transfer routes (inbound gate → outbound gate) per booking group, computed by the v2 engine.
    Not live tracking: these are planned routes for the passengers' recorded connections."""
    from services.routing_engine import get_engine, profile_for
    eng = get_engine()
    q = ("SELECT p.booking_ref, p.lead_name, p.needs, p.inbound, p.outbound, fi.gate ig, fo.gate og, fo.status ost "
         "FROM passengers p JOIN flights fi ON fi.flight_no=p.inbound JOIN flights fo ON fo.flight_no=p.outbound")
    args = ()
    if flight_no:
        q += " WHERE p.inbound=? OR p.outbound=?"
        args = (flight_no, flight_no)
    groups = {}
    for p in query(q, args):
        if not p["ig"] or not p["og"] or p["ost"] == "CANCELLED":
            continue
        needs = _j(p["needs"], [])
        prof = profile_for(needs)
        k = (p["ig"], p["og"], prof)
        groups.setdefault(k, {"bookings": [], "needs": set()})
        groups[k]["bookings"].append(p["booking_ref"])
        groups[k]["needs"] |= set(needs)
    out = []
    for (a, b, prof), g in list(groups.items())[:limit]:
        r = _route(eng, a, b, prof)
        r.update(bookings=g["bookings"], needs=sorted(g["needs"]))
        out.append(r)
    return out


def baggage_paths(flight_no=None):
    """Bag movement legs: inbound aircraft gate → transfer sortation → assigned departure gate (from records)."""
    q = ("SELECT a.bag_tag, a.booking_ref, a.flight_no, a.kind, b.origin_flight AS inbound_flight, fi.gate ig, fo.gate og, "
         "p.outbound pax_flight FROM bag_flight_assignments a JOIN baggage_items b USING(bag_tag) "
         "LEFT JOIN flights fi ON fi.flight_no=b.origin_flight LEFT JOIN flights fo ON fo.flight_no=a.flight_no "
         "LEFT JOIN passengers p ON p.booking_ref=a.booking_ref WHERE a.status='ACTIVE'")
    args = ()
    if flight_no:
        q += " AND (a.flight_no=? OR b.origin_flight=? OR p.outbound=?)"
        args = (flight_no, flight_no, flight_no)
    legs = {}
    for r in query(q, args):
        k = (r["ig"], r["og"], r["kind"], r["flight_no"], r["pax_flight"])
        legs.setdefault(k, []).append(r["bag_tag"])
    return [{"from_gate": k[0], "to_gate": k[1], "kind": k[2], "bag_flight": k[3], "passenger_flight": k[4],
             "bags": v, "discrepancy": k[2] == "SEPARATE"} for k, v in legs.items()]


def recovery_metrics():
    k = kpis(flights_state())
    vuln_tx = query_one("SELECT COUNT(*) n FROM rebooking_batches WHERE kind='PRIORITY' AND status='COMMITTED'")["n"]
    vuln_pax = query_one("SELECT COALESCE(SUM(passenger_count),0) n FROM rebooking_batches WHERE kind='PRIORITY' AND "
                         "status='COMMITTED'")["n"]
    return {
        "affected_passengers": k["affected_passengers"] + k["rebooked_passengers"],
        "vulnerable_prioritised": vuln_pax, "priority_transactions": vuln_tx,
        "rebooking_transactions": query_one("SELECT COUNT(*) n FROM rebooking_transactions")["n"],
        "successful_batches": query_one("SELECT COUNT(*) n FROM rebooking_batches WHERE status='COMMITTED'")["n"],
        "failed_batches": query_one("SELECT COUNT(*) n FROM rebooking_batches WHERE status IN ('ESCALATED','FAILED',"
                                    "'ROLLED_BACK')")["n"],
        "crew_validations": query_one("SELECT COUNT(*) n FROM audit_events WHERE event_type='CREW_LEGALITY_EVALUATED' "
                                      "AND event_id > COALESCE((SELECT MAX(event_id) FROM audit_events WHERE "
                                      "event_type='DEMO_RESET'),0)")["n"],
        "maintenance_blocks": query_one("SELECT COUNT(*) n FROM departure_holds WHERE hold_type='MAINTENANCE' AND "
                                        "status='ACTIVE'")["n"],
        "baggage_plans": query_one("SELECT COUNT(*) n FROM baggage_delivery_notes WHERE status='ISSUED'")["n"],
        "gate_conflicts": query_one("SELECT COUNT(*) n FROM approval_requests WHERE status='STALE'")["n"],
        "pending_approvals": k["pending_approvals"],
        "completed_actions": query_one("SELECT COUNT(*) n FROM operational_actions")["n"]
        + query_one("SELECT COUNT(*) n FROM crew_assignment_proposals WHERE status='APPROVED_EXECUTED'")["n"]
        + query_one("SELECT COUNT(*) n FROM journey_approvals WHERE status='APPROVED_EXECUTED'")["n"],
        "label": "SYNTHETIC SCENARIO RESULTS",
    }
