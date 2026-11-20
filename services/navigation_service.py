"""NAVIGATION SERVICE — persistent routes and step-by-step progress for each booking.

* Routes are computed by the shared graph engine and stored in navigation_routes.
* A stored route is re-used until something material changes: destination gate, starting point,
  routing profile, or the terminal graph itself (closures/re-openings). Then it is recalculated,
  the old route is superseded, and the reason is recorded.
* Progress (Start, Previous, Mark completed) is stored in route_progress, so it survives reruns.
"""
import json

from db import query_one, tx, utcnow
from services.routing_engine import NoRouteError, get_engine


def _store(con, booking_ref, route, dest_gate, reason):
    con.execute("UPDATE navigation_routes SET superseded_at=? WHERE booking_ref=? AND superseded_at IS NULL",
                (utcnow(), booking_ref))
    cur = con.execute(
        "INSERT INTO navigation_routes(booking_ref,origin_node,dest_gate,profile,distance_m,steps_json,path_json,"
        "accessible_verified,graph_version,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (booking_ref, route.origin, dest_gate, route.profile, route.distance_m,
         json.dumps([s.__dict__ for s in route.steps]),
         json.dumps({"nodes": route.node_path, "edges": route.edge_path}),
         int(route.accessible_verified), route.graph_version, reason, utcnow()))
    rid = cur.lastrowid
    con.execute("INSERT INTO route_progress(booking_ref, route_id, step_index, started, updated_at) "
                "VALUES(?,?,0,0,?) ON CONFLICT(booking_ref) DO UPDATE SET route_id=excluded.route_id, "
                "step_index=0, started=0, updated_at=excluded.updated_at", (booking_ref, rid, utcnow()))
    return rid


def current_route(booking_ref, origin_node, dest_gate, profile):
    """Return the passenger's active route, recalculating only when needed.
    Returns dict(route=..., recalculated=bool, reason=str|None, error=str|None)."""
    engine = get_engine()
    stored = query_one("SELECT * FROM navigation_routes WHERE booking_ref=? AND superseded_at IS NULL "
                       "ORDER BY route_id DESC LIMIT 1", (booking_ref,))
    reason = None
    if stored is None:
        reason = "Route calculated"
    elif stored["dest_gate"] != dest_gate:
        reason = f"Gate changed from {stored['dest_gate']} to {dest_gate} — route recalculated"
    elif stored["origin_node"] != origin_node:
        reason = "Starting point updated — route recalculated"
    elif stored["profile"] != profile:
        reason = f"Routing profile changed to {profile} — route recalculated"
    elif stored["graph_version"] != engine.graph_version:
        reason = "Terminal conditions changed (corridor or lift availability) — route recalculated"
    if reason is None:
        return {"route": _load(stored), "recalculated": False, "reason": None, "error": None}
    try:
        route = engine.shortest_path(origin_node, dest_gate, profile)
    except NoRouteError as e:
        with tx() as con:
            con.execute("UPDATE navigation_routes SET superseded_at=? WHERE booking_ref=? AND superseded_at IS NULL",
                        (utcnow(), booking_ref))
            con.execute("INSERT INTO audit_log(actor,action,detail,created_at) VALUES('system','ROUTE_UNAVAILABLE',?,?)",
                        (json.dumps({"booking": booking_ref, "error": str(e)}), utcnow()))
        return {"route": None, "recalculated": True, "reason": reason, "error": str(e)}
    with tx() as con:
        rid = _store(con, booking_ref, route, dest_gate, reason)
        if stored is not None:
            con.execute("INSERT INTO audit_log(actor,action,detail,created_at) VALUES('system','ROUTE_RECALCULATED',?,?)",
                        (json.dumps({"booking": booking_ref, "reason": reason}), utcnow()))
    return {"route": _load(query_one("SELECT * FROM navigation_routes WHERE route_id=?", (rid,))),
            "recalculated": stored is not None, "reason": reason, "error": None}


def preview_route(origin_node, dest_gate, profile):
    """Read-only route (used by the coordinator view); never touches passenger progress."""
    try:
        r = get_engine().shortest_path(origin_node, dest_gate, profile)
        return {"route": dict(r.to_dict(), steps=[s.__dict__ for s in r.steps]), "error": None}
    except NoRouteError as e:
        return {"route": None, "error": str(e)}


def _load(row):
    path = json.loads(row["path_json"])
    if isinstance(path, list):  # tolerate the older nodes-only format
        path = {"nodes": path, "edges": None}
    return {"route_id": row["route_id"], "origin": row["origin_node"], "dest_gate": row["dest_gate"],
            "profile": row["profile"], "distance_m": row["distance_m"], "steps": json.loads(row["steps_json"]),
            "node_path": path["nodes"], "edge_path": path["edges"], "accessible_verified": bool(row["accessible_verified"]),
            "graph_version": row["graph_version"], "reason": row["reason"], "created_at": row["created_at"]}


# ---------------------------------------------------------------- progress
def progress(booking_ref):
    row = query_one("SELECT * FROM route_progress WHERE booking_ref=?", (booking_ref,))
    return row or {"booking_ref": booking_ref, "step_index": 0, "started": 0}


def start(booking_ref):
    _update(booking_ref, "started=1, step_index=0")


def move(booking_ref, delta, n_steps):
    p = progress(booking_ref)
    idx = max(0, min(n_steps - 1, int(p.get("step_index") or 0) + delta))
    _update(booking_ref, "started=1, step_index=?", (idx,))
    return idx


def _update(booking_ref, set_sql, args=()):
    with tx() as con:
        con.execute("INSERT OR IGNORE INTO route_progress(booking_ref, step_index, started, updated_at) "
                    "VALUES(?,0,0,?)", (booking_ref, utcnow()))
        con.execute(f"UPDATE route_progress SET {set_sql}, updated_at=? WHERE booking_ref=?",
                    (*args, utcnow(), booking_ref))


def force_recalculate(booking_ref):
    with tx() as con:
        con.execute("UPDATE navigation_routes SET superseded_at=? WHERE booking_ref=? AND superseded_at IS NULL",
                    (utcnow(), booking_ref))
