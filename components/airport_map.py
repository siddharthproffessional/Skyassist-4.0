"""Illustrative terminal map (SVG) — shared by the passenger and coordinator portals.

Drawn from the same terminal_nodes / terminal_edges tables the routing engine uses, so the highlighted
route is exactly the computed route. Geometry is schematic and synthetic, not a surveyed floor plan.
"""
import html
import json

from services.routing_engine import CON_Y, HUB_X, HUB_Y

W, H = 960, 650
EDGE_STYLE = {
    "CONCOURSE": 'stroke="#c9d3e3" stroke-width="10" stroke-linecap="round"',
    "CONNECTOR": 'stroke="#9fb7dc" stroke-width="9" stroke-linecap="round"',
    "VERTICAL": 'stroke="#b8c4d6" stroke-width="5" stroke-dasharray="2 4"',
    "SPUR": 'stroke="#d5dce8" stroke-width="4"',
    "STAIRS": 'stroke="#e0a458" stroke-width="5" stroke-dasharray="9 6"',
}


def _pts_for_edge(e, nodes, a, b):
    if e.get("geometry"):
        pts = json.loads(e["geometry"])
        if a != e["from_node"]:
            pts = list(reversed(pts))
        return pts
    return [[nodes[a]["x"], nodes[a]["y"]], [nodes[b]["x"], nodes[b]["y"]]]


def _path_d(points):
    return "M" + " L".join(f"{x:.0f} {y:.0f}" for x, y in points)


def render_map(nodes, edges, route=None, current_step=None, show_all_labels=True, title=None):
    nodes = {n["node_id"]: n for n in nodes}
    edges_by_id = {e["edge_id"]: e for e in edges}
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="Illustrative terminal map{": " + html.escape(title) if title else ""}" '
           f'style="width:100%;height:auto;display:block;font-family:Inter,system-ui,sans-serif">',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" '
           'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#ffffff"/></marker></defs>',
           f'<rect x="0" y="0" width="{W}" height="{H}" rx="18" fill="#f6f8fc"/>',
           f'<rect x="12" y="{CON_Y - 26}" width="{W - 24}" height="{H - CON_Y + 14}" rx="12" fill="#eaf0fa"/>',
           f'<text x="26" y="{CON_Y - 8}" font-size="12" fill="#5a6b85" font-weight="600">LEVEL 2 · Skywalk connectors</text>',
           f'<text x="26" y="40" font-size="12" fill="#5a6b85" font-weight="600">LEVEL 1 · Gates &amp; hubs</text>']
    for c, x in HUB_X.items():
        out.append(f'<text x="{x}" y="64" text-anchor="middle" font-size="17" font-weight="700" fill="#0b2545">'
                   f'Concourse {c}</text>')
    # edges
    on_route = set(route["edge_path"]) if route and route.get("edge_path") else set()
    for e in edges:
        pts = _pts_for_edge(e, nodes, e["from_node"], e["to_node"])
        style = EDGE_STYLE.get(e["kind"], EDGE_STYLE["SPUR"])
        if not int(e.get("available", 1)):
            style = 'stroke="#e5484d" stroke-width="6" stroke-dasharray="6 6"'
        if e["kind"] == "VERTICAL" and int(e["elevator"]):
            pts = [[p[0] + 9, p[1]] for p in pts]
        out.append(f'<path d="{_path_d(pts)}" fill="none" {style}/>')
        if not int(e.get("available", 1)):
            mx, my = pts[len(pts) // 2] if len(pts) > 2 else ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
            out.append(f'<g><circle cx="{mx}" cy="{my}" r="11" fill="#e5484d"/><text x="{mx}" y="{my + 4}" '
                       f'text-anchor="middle" font-size="13" font-weight="800" fill="#fff">✕</text></g>')
    stairs = [e for e in edges if e["kind"] == "STAIRS"]
    for e in stairs:
        pts = json.loads(e["geometry"]) if e.get("geometry") else None
        if pts:
            out.append(f'<text x="{pts[1][0]}" y="{pts[1][1] - 10}" text-anchor="middle" font-size="11" '
                       f'fill="#b26a12">stairs only</text>')
    out.append(f'<text x="{(HUB_X["A"] + HUB_X["B"]) / 2}" y="{CON_Y - 10}" text-anchor="middle" font-size="11" '
               f'fill="#4b6890">Skywalk A–B · 500 m</text>')
    out.append(f'<text x="{(HUB_X["B"] + HUB_X["C"]) / 2}" y="{CON_Y - 10}" text-anchor="middle" font-size="11" '
               f'fill="#4b6890">Skywalk B–C · 600 m</text>')
    out.append(f'<text x="{(HUB_X["A"] + HUB_X["C"]) / 2}" y="630" text-anchor="middle" font-size="11" '
               f'fill="#4b6890">Outer step-free corridor A–C · 1,300 m (cart lane)</text>')

    # route
    if route and route.get("node_path"):
        path_nodes, epath = route["node_path"], route["edge_path"] if route.get("edge_path") else None
        seg_pts = []
        for i in range(len(path_nodes) - 1):
            a, b = path_nodes[i], path_nodes[i + 1]
            e = edges_by_id.get(epath[i]) if epath else None
            pts = _pts_for_edge(e, nodes, a, b) if e else [[nodes[a]["x"], nodes[a]["y"]], [nodes[b]["x"], nodes[b]["y"]]]
            seg_pts.append(((a, b), pts))
        all_pts = []
        for _, pts in seg_pts:
            all_pts.extend(pts if not all_pts else pts[1:])
        out.append(f'<path d="{_path_d(all_pts)}" fill="none" stroke="#1d4ed8" stroke-width="9" '
                   f'stroke-linecap="round" stroke-linejoin="round" opacity=".95"/>')
        # direction arrows on every segment
        for _, pts in seg_pts:
            for j in range(len(pts) - 1):
                (x1, y1), (x2, y2) = pts[j], pts[j + 1]
                if abs(x2 - x1) + abs(y2 - y1) < 30:
                    continue
                out.append(f'<path d="M{x1:.0f} {y1:.0f} L{(x1 + x2) / 2:.0f} {(y1 + y2) / 2:.0f}" stroke="none" '
                           f'fill="none" marker-end="url(#arr)"/>')
        # completed + current step overlays
        steps = route.get("steps") or []
        if current_step is not None and steps:
            done_nodes = set()
            for s in steps[:current_step]:
                done_nodes.update(s.get("path_nodes") or [])
            cur = steps[min(current_step, len(steps) - 1)]
            cur_nodes = cur.get("path_nodes") or []
            for (a, b), pts in seg_pts:
                if a in cur_nodes and b in cur_nodes and len(cur_nodes) > 1:
                    out.append(f'<path d="{_path_d(pts)}" fill="none" stroke="#f59e0b" stroke-width="11" '
                               f'stroke-linecap="round"/>')
                elif a in done_nodes and b in done_nodes:
                    out.append(f'<path d="{_path_d(pts)}" fill="none" stroke="#7fa7e8" stroke-width="9" '
                               f'stroke-linecap="round"/>')
            if len(cur_nodes) == 1 and cur_nodes[0] in nodes:
                n = nodes[cur_nodes[0]]
                out.append(f'<circle cx="{n["x"]}" cy="{n["y"]}" r="14" fill="none" stroke="#f59e0b" stroke-width="4"/>')
    route_nodes = set(route["node_path"]) if route and route.get("node_path") else set()

    # nodes
    for nid, n in nodes.items():
        x, y, t = n["x"], n["y"], n["node_type"]
        if t == "GATE":
            num = int(n["name"][-2:])
            bold = nid in route_nodes
            out.append(f'<circle cx="{x}" cy="{y}" r="{4.5 if not bold else 5.5}" fill="{"#1d4ed8" if bold else "#7a8aa6"}"/>')
            if show_all_labels or bold:
                dx = -12 if num % 2 else 12
                out.append(f'<text x="{x + dx}" y="{y + 3.5}" text-anchor="{"end" if dx < 0 else "start"}" '
                           f'font-size="{10 if bold else 9}" font-weight="{700 if bold else 500}" '
                           f'fill="{"#0b2545" if bold else "#6b7a93"}">{n["name"][5:]}</text>')
        elif t == "HUB":
            out.append(f'<rect x="{x - 34}" y="{y - 13}" width="68" height="26" rx="13" fill="#0b2545"/>'
                       f'<text x="{x}" y="{y + 4.5}" text-anchor="middle" font-size="11.5" font-weight="700" '
                       f'fill="#fff">{n["concourse"]} HUB</text>')
        elif t == "CONNECTOR":
            out.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#fff" stroke="#4b6890" stroke-width="3"/>'
                       f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="9" font-weight="800" fill="#4b6890">⇅</text>')
        elif t == "CHECKPOINT":
            out.append(f'<rect x="{x - 9}" y="{y - 9}" width="18" height="18" rx="4" fill="#475569"/>'
                       f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="800" fill="#fff">S</text>'
                       f'<text x="{x}" y="{y + 22}" text-anchor="middle" font-size="9" fill="#475569">Security</text>')
        elif t == "TRANSFER_DESK":
            out.append(f'<rect x="{x - 13}" y="{y - 9}" width="26" height="18" rx="5" fill="#0e7490"/>'
                       f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="9.5" font-weight="800" fill="#fff">TD</text>')
        elif t == "ASSISTANCE_POINT":
            out.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#2563eb"/>'
                       f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="800" fill="#fff">♿</text>')

    # start / destination markers
    if route and route.get("node_path"):
        s, d = nodes[route["node_path"][0]], nodes[route["node_path"][-1]]
        out.append(f'<g><circle cx="{s["x"]}" cy="{s["y"]}" r="13" fill="#16a34a" stroke="#fff" stroke-width="3"/>'
                   f'<rect x="{s["x"] - 30}" y="{s["y"] - 40}" width="60" height="20" rx="10" fill="#16a34a"/>'
                   f'<text x="{s["x"]}" y="{s["y"] - 26}" text-anchor="middle" font-size="11" font-weight="800" '
                   f'fill="#fff">START</text></g>')
        label = html.escape(d["name"].replace("Gate ", ""))
        out.append(f'<g><path d="M{d["x"]} {d["y"]} l-13 -22 a15 15 0 1 1 26 0 z" fill="#0b2545" stroke="#fff" '
                   f'stroke-width="2.5"/><text x="{d["x"]}" y="{d["y"] - 27}" text-anchor="middle" font-size="10" '
                   f'font-weight="800" fill="#fff">{label[:4]}</text></g>')
    out.append(f'<text x="{W - 20}" y="40" text-anchor="end" font-size="10.5" fill="#7a8aa6">'
               f'Illustrative schematic from synthetic data · not a surveyed floor plan · not to scale</text>')
    out.append("</svg>")
    return "".join(out)


LEGEND_HTML = (
    '<div class="sa-legend"><span><i style="background:#1d4ed8"></i>Your route</span>'
    '<span><i style="background:#f59e0b"></i>Current step</span><span><i style="background:#7fa7e8"></i>Completed</span>'
    '<span><i style="background:#16a34a"></i>Start</span><span><i style="background:#0b2545"></i>Destination</span>'
    '<span><i style="background:#e0a458"></i>Stairs only</span><span><i style="background:#e5484d"></i>Closed</span>'
    '<span><b>S</b> Security</span><span><b>TD</b> Transfer Desk</span><span>♿ Assistance point</span></div>')
