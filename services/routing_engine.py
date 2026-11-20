"""INDOOR ROUTING ENGINE — graph + Dijkstra, independent of any UI.

The terminal is modelled as a graph of nodes (gates, hubs, checkpoints, desks, lifts, connectors) and
edges (corridors, skywalks, lifts, escalators, stairs). Walking distance always comes from summing
edge lengths along the chosen path — never from straight-line distance between map coordinates.

The geometry is ILLUSTRATIVE and SYNTHETIC: it reproduces the distances of the original SkyAssist
dataset (50 m between gates, A↔B 500 m, B↔C 600 m) but is not a surveyed airport floor plan.

Profiles
  STANDARD   any available, unrestricted edge
  STEP_FREE  accessible edges only (no stairs, no escalators) — wheelchair, stroller, elderly
  CART       step-free AND cart-permitted edges — priority mobility cart
"""
import hashlib
import heapq
import json
from dataclasses import dataclass, field

from db import connect

GATE_SPACING_M = 50
CONCOURSE_GATES = {"A": 20, "B": 20, "C": 22}
HUB_X = {"A": 180, "B": 480, "C": 780}
HUB_Y, CON_Y = 470, 560
PROFILES = ("STANDARD", "STEP_FREE", "CART")


class NoRouteError(Exception):
    """Raised when no valid route exists for the requested profile. Never fabricate a route."""

    def __init__(self, message, reason="NO_ROUTE"):
        super().__init__(message)
        self.reason = reason


# ----------------------------------------------------------------------------- synthetic graph
def gate_node(gate: str) -> str:
    return f"G_{gate}"


def build_synthetic_graph():
    """Return (nodes, edges) for the illustrative terminal. Used by the migration seeder."""
    nodes, edges = [], []

    def node(node_id, name, ntype, conc, floor, x, y):
        nodes.append(dict(node_id=node_id, name=name, node_type=ntype, concourse=conc, floor=floor, x=x, y=y))

    def edge(eid, a, b, dist, desc, accessible=1, stairs=0, escalator=0, elevator=0, restricted=0, cart_ok=1,
             kind="CORRIDOR", geometry=None):
        edges.append(dict(edge_id=eid, from_node=a, to_node=b, distance_m=float(dist),
                          estimated_walk_time=round(dist / 80, 2), accessible=accessible, stairs=stairs,
                          escalator=escalator, elevator=elevator, restricted=restricted, cart_ok=cart_ok,
                          direction_description=desc, kind=kind,
                          geometry=json.dumps(geometry) if geometry else None))

    for c, n in CONCOURSE_GATES.items():
        hx = HUB_X[c]
        node(f"HUB_{c}", f"Concourse {c} hub", "HUB", c, 1, hx, HUB_Y)
        node(f"SEC_{c}", f"Transfer security {c}", "CHECKPOINT", c, 1, hx - 52, HUB_Y + 28)
        node(f"TD_{c}", f"Transfer Desk {c}", "TRANSFER_DESK", c, 1, hx + 52, HUB_Y + 18)
        node(f"AP_{c}", f"Special Assistance point {c}", "ASSISTANCE_POINT", c, 1, hx + 52, HUB_Y + 46)
        node(f"CON_{c}", f"Skywalk station {c} (Level 2)", "CONNECTOR", c, 2, hx, CON_Y)
        for i in range(1, n + 1):
            node(gate_node(f"{c}{i:02d}"), f"Gate {c}{i:02d}", "GATE", c, 1, hx, HUB_Y - i * 17)
        # gate spine
        edge(f"E_{c}01_HUB", gate_node(f"{c}01"), f"HUB_{c}", GATE_SPACING_M,
             f"Concourse {c} gate corridor", kind="CONCOURSE")
        for i in range(1, n):
            edge(f"E_{c}{i:02d}_{c}{i + 1:02d}", gate_node(f"{c}{i:02d}"), gate_node(f"{c}{i + 1:02d}"),
                 GATE_SPACING_M, f"Concourse {c} gate corridor", kind="CONCOURSE")
        # landmarks just off the hub (20 m)
        edge(f"E_HUB_{c}_SEC", f"HUB_{c}", f"SEC_{c}", 20, f"Transfer security {c}", kind="SPUR")
        edge(f"E_HUB_{c}_TD", f"HUB_{c}", f"TD_{c}", 20, f"Transfer Desk {c}", kind="SPUR")
        edge(f"E_HUB_{c}_AP", f"HUB_{c}", f"AP_{c}", 20, f"Special Assistance point {c}", kind="SPUR")
        # vertical circulation between Level 1 hub and Level 2 skywalk station (no horizontal distance)
        edge(f"E_ESC_{c}", f"HUB_{c}", f"CON_{c}", 0, f"escalator at Concourse {c} hub", accessible=0,
             escalator=1, cart_ok=0, kind="VERTICAL")
        edge(f"E_ELV_{c}", f"HUB_{c}", f"CON_{c}", 0, f"step-free lift at Concourse {c} hub", elevator=1,
             kind="VERTICAL")

    edge("E_SKY_AB", "CON_A", "CON_B", 500, "Skywalk A–B", kind="CONNECTOR")
    edge("E_SKY_BC", "CON_B", "CON_C", 600, "Skywalk B–C", kind="CONNECTOR")
    edge("E_OUTER_AC", "CON_A", "CON_C", 1300, "Outer service corridor A–C (step-free, cart lane)",
         kind="CONNECTOR", geometry=[[HUB_X["A"], CON_Y], [HUB_X["A"], 612], [HUB_X["C"], 612], [HUB_X["C"], CON_Y]])
    edge("E_STAIRS_B03_C08", gate_node("B03"), gate_node("C08"), 500, "Mezzanine stairway B03–C08 (stairs only)",
         accessible=0, stairs=1, cart_ok=0, kind="STAIRS",
         geometry=[[HUB_X["B"], HUB_Y - 3 * 17], [630, 385], [HUB_X["C"], HUB_Y - 8 * 17]])
    return nodes, edges


# ----------------------------------------------------------------------------- data classes
@dataclass
class RouteStep:
    index: int
    text: str
    distance_m: float
    cumulative_m: float
    kind: str
    from_node: str
    to_node: str
    path_nodes: list = field(default_factory=list)


@dataclass
class Route:
    origin: str
    destination: str
    profile: str
    distance_m: float
    node_path: list
    edge_path: list
    steps: list
    accessible_verified: bool
    graph_version: str

    def to_dict(self):
        return dict(origin=self.origin, destination=self.destination, profile=self.profile,
                    distance_m=self.distance_m, node_path=self.node_path, edge_path=self.edge_path,
                    steps=[s.__dict__ for s in self.steps], accessible_verified=self.accessible_verified,
                    graph_version=self.graph_version)


# ----------------------------------------------------------------------------- engine
class RoutingEngine:
    def __init__(self, nodes=None, edges=None):
        if nodes is None or edges is None:
            nodes, edges = self.load_from_db()
        self.nodes = {n["node_id"]: n for n in nodes}
        self.edges = {e["edge_id"]: e for e in edges}
        self.adj = {}
        for e in edges:
            self.adj.setdefault(e["from_node"], []).append((e["to_node"], e["edge_id"]))
            self.adj.setdefault(e["to_node"], []).append((e["from_node"], e["edge_id"]))
        sig = "|".join(f"{e['edge_id']}:{int(e.get('available', 1))}:{e['distance_m']}" for e in sorted(
            edges, key=lambda x: x["edge_id"]))
        self.graph_version = hashlib.sha1(sig.encode()).hexdigest()[:10]

    @staticmethod
    def load_from_db():
        con = connect()
        try:
            nodes = [dict(r) for r in con.execute("SELECT * FROM terminal_nodes")]
            edges = [dict(r) for r in con.execute("SELECT * FROM terminal_edges")]
        finally:
            con.close()
        return nodes, edges

    # -- edge rules
    @staticmethod
    def edge_allowed(e, profile):
        if not int(e.get("available", 1)) or int(e.get("restricted", 0)):
            return False
        if profile in ("STEP_FREE", "CART") and (not int(e["accessible"]) or int(e["stairs"]) or int(e["escalator"])):
            return False
        if profile == "CART" and not int(e["cart_ok"]):
            return False
        return True

    @staticmethod
    def _tie_break(e, profile):
        # Same distance: walkers prefer the escalator, step-free users must take the lift.
        if profile == "STANDARD" and int(e["elevator"]):
            return 0.001
        return 0.0

    def resolve_node(self, place: str) -> str:
        if place in self.nodes:
            return place
        if gate_node(place) in self.nodes:
            return gate_node(place)
        raise NoRouteError(f"Unknown location '{place}' in the terminal map.", "UNKNOWN_LOCATION")

    def shortest_path(self, origin: str, destination: str, profile: str = "STANDARD") -> Route:
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {PROFILES}")
        if not destination:
            raise NoRouteError("No verified destination gate is available, so no route can be calculated.",
                               "NO_DESTINATION")
        src, dst = self.resolve_node(origin), self.resolve_node(destination)
        dist = {src: 0.0}
        cost = {src: 0.0}
        prev = {}
        heap = [(0.0, src)]
        while heap:
            c, node = heapq.heappop(heap)
            if c > cost.get(node, float("inf")):
                continue
            if node == dst:
                break
            for nxt, eid in self.adj.get(node, []):
                e = self.edges[eid]
                if not self.edge_allowed(e, profile):
                    continue
                nc = c + e["distance_m"] + self._tie_break(e, profile)
                if nc < cost.get(nxt, float("inf")):
                    cost[nxt] = nc
                    dist[nxt] = dist[node] + e["distance_m"]
                    prev[nxt] = (node, eid)
                    heapq.heappush(heap, (nc, nxt))
        if dst not in dist:
            label = {"STEP_FREE": "step-free (accessible)", "CART": "mobility-cart"}.get(profile, "walking")
            raise NoRouteError(
                f"No {label} route from {self.nodes[src]['name']} to {self.nodes[dst]['name']} can be verified "
                f"with the current terminal data (a corridor or lift may be closed).", "NO_ROUTE")
        node_path, edge_path = [dst], []
        while node_path[-1] != src:
            p, eid = prev[node_path[-1]]
            edge_path.append(eid)
            node_path.append(p)
        node_path.reverse()
        edge_path.reverse()
        steps = self._instructions(node_path, edge_path)
        return Route(origin=src, destination=dst, profile=profile, distance_m=dist[dst], node_path=node_path,
                     edge_path=edge_path, steps=steps, accessible_verified=profile in ("STEP_FREE", "CART"),
                     graph_version=self.graph_version)

    def nearest(self, origin: str, node_types, profile="STANDARD"):
        """Nearest node of the given type(s) by walking distance (e.g. Transfer Desk)."""
        best = None
        for nid, n in self.nodes.items():
            if n["node_type"] in node_types:
                try:
                    r = self.shortest_path(origin, nid, profile)
                except NoRouteError:
                    continue
                if best is None or r.distance_m < best.distance_m:
                    best = r
        if best is None:
            raise NoRouteError("No reachable assistance point could be verified.", "NO_ROUTE")
        return best

    # -- human-readable directions
    def _instructions(self, node_path, edge_path):
        groups = []  # consecutive edges of the same kind/concourse merged into one instruction
        for i, eid in enumerate(edge_path):
            e = self.edges[eid]
            a, b = node_path[i], node_path[i + 1]
            key = (e["kind"], self.nodes[a]["concourse"] if e["kind"] in ("CONCOURSE",) else eid)
            if groups and groups[-1]["key"] == key:
                g = groups[-1]
                g["dist"] += e["distance_m"]
                g["to"] = b
                g["nodes"].append(b)
            else:
                groups.append(dict(key=key, kind=e["kind"], edge=e, dist=e["distance_m"], frm=a, to=b, nodes=[a, b]))
        steps, cum = [], 0.0
        first = self.nodes[node_path[0]]
        if first["node_type"] == "GATE":
            steps.append(RouteStep(1, f"Exit at {first['name']} and follow the purple ‘Flight Connections’ signs.",
                                   0, 0, "START", node_path[0], node_path[0], [node_path[0]]))
        for g in groups:
            fn, tn = self.nodes[g["frm"]], self.nodes[g["to"]]
            e, d = g["edge"], int(round(g["dist"]))
            if g["kind"] == "CONCOURSE":
                text = f"Walk {d} m along Concourse {fn['concourse']} to {tn['name']}."
                if tn["node_type"] == "HUB":
                    text += f" Transfer screening is at the checkpoint beside the hub (fast-track for assisted passengers)."
            elif g["kind"] == "VERTICAL":
                up = tn["floor"] > fn["floor"]
                how = "Take the step-free lift" if int(e["elevator"]) else "Take the escalator"
                text = f"{how} {'up to Level 2 (Skywalk)' if up else 'down to Level 1'} at Concourse {fn['concourse']} hub."
            elif g["kind"] == "CONNECTOR":
                text = f"Follow the {e['direction_description']} towards Concourse {tn['concourse']} ({d} m)."
            elif g["kind"] == "STAIRS":
                text = f"Take the {e['direction_description']} to {tn['name']} ({d} m, stairs)."
            elif g["kind"] == "SPUR":
                text = f"Go to {tn['name']} ({d} m, beside Concourse {fn['concourse']} hub)."
            else:
                text = f"Continue {d} m to {tn['name']}."
            cum += g["dist"]
            steps.append(RouteStep(len(steps) + 1, text, g["dist"], cum, g["kind"], g["frm"], g["to"], g["nodes"]))
        if steps and steps[0].kind == "START" and not any("screening" in s.text for s in steps):
            steps[0].text += " Clear transfer screening at the nearest checkpoint on the way (time included)."
        last = self.nodes[node_path[-1]]
        steps.append(RouteStep(len(steps) + 1, f"Arrive at {last['name']}.", 0, cum, "ARRIVE",
                               node_path[-1], node_path[-1], [node_path[-1]]))
        return steps


def profile_for(needs, mode="SELF"):
    """Map passenger needs / transfer mode to a routing profile."""
    needs = set(needs or [])
    if mode == "CART":
        return "CART"
    if needs & {"WCHR", "STROLLER", "ELDERLY"}:
        return "STEP_FREE"
    return "STANDARD"


def get_engine() -> RoutingEngine:
    """Engine built from the live terminal tables, so closures and reopenings apply immediately."""
    return RoutingEngine()
