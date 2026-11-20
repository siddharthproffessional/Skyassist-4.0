"""/operations — connection board, synthetic-data simulator and audit log (coordinators only)."""
import pandas as pd
import streamlit as st

import build_db
from components import ui
from components.airport_map import LEGEND_HTML, render_map
from components.session import nav_link, require_login, sign_out
from db import local_time, query
from services import coordinator_service as cs
from services.auth_service import COORDINATOR
from services.routing_engine import RoutingEngine

ui.inject(ui.COORDINATOR_CSS)
p = require_login(COORDINATOR, "Operations sign-in", "Airport terminal coordinators only.",
                  ["`sarah` / `aisha`, password `coord123`"])

with st.sidebar:
    st.markdown("### ✈️ SkyAssist Ops")
    st.caption(f"Signed in as **{p.display_name}**")
    nav_link("views/coordinator.py", "Assistance requests", "🛟")
    nav_link("views/operations.py", "Operations overview", "📊")
    st.divider()
    if st.button("Sign out", use_container_width=True):
        sign_out(COORDINATOR)
        st.rerun()

ui.md('<div style="font-size:26px;font-weight:800;color:#0b2545">Operations overview</div>'
      '<div class="sa-muted">Every value below is computed live from the database by the deterministic engine.</div>')

board = cs.connection_board(p)
st.markdown("#### All connections")
st.dataframe(pd.DataFrame([{
    "Booking": b["booking_ref"], "Passenger": b["passenger"], "Needs": ", ".join(b["needs"]) or "—",
    "Inbound": b["inbound"], "Outbound": b["outbound"] or "—", "Arr gate": b.get("arr_gate", "—"),
    "Dep gate": b.get("dep_gate", "—"), "Min left": b.get("minutes_left"), "Alone (min)": b.get("self_min"),
    "Assisted (min)": b.get("assisted_min"), "Risk on own": b.get("risk_self", b["state"]),
    "Policy": b.get("decision", b["state"])} for b in board]), use_container_width=True, hide_index=True)

eng = RoutingEngine()
st.markdown("#### Terminal map (current conditions)")
ui.md(render_map(list(eng.nodes.values()), list(eng.edges.values()), None))
ui.md(LEGEND_HTML)

st.markdown("#### Synthetic data simulator")
st.warning("Demonstration controls. In production, gate changes and corridor status come from airport systems "
           "(AODB, facilities, SkyOps Twin) — none are connected in this build.")
c1, c2 = st.columns(2)
with c1:
    with st.form("gate_change"):
        st.markdown("**Change a departure gate**")
        deps = [f["flight_no"] for f in query("SELECT flight_no FROM flights WHERE direction='DEPARTURE' AND "
                                               "status!='CANCELLED' ORDER BY flight_no")]
        fl = st.selectbox("Flight", deps)
        gates = [g["gate"] for g in query("SELECT gate FROM gates ORDER BY gate")]
        g = st.selectbox("New gate", gates)
        if st.form_submit_button("Apply gate change", use_container_width=True):
            try:
                cs.simulate_gate_change(p, fl, g)
                st.success(f"{fl} now departs from {g}. Affected passengers' routes will recalculate.")
            except ValueError as e:
                st.error(str(e))
with c2:
    with st.form("corridor"):
        st.markdown("**Close or reopen a corridor / lift**")
        edges = [e for e in eng.edges.values() if e["kind"] in ("CONNECTOR", "VERTICAL", "STAIRS")]
        eid = st.selectbox("Corridor", [e["edge_id"] for e in edges],
                           format_func=lambda x: f'{eng.edges[x]["direction_description"]} '
                                                 f'({"open" if int(eng.edges[x].get("available", 1)) else "CLOSED"})')
        reason = st.text_input("Reason", "Maintenance")
        a, b = st.columns(2)
        close = a.form_submit_button("Close", use_container_width=True)
        reopen = b.form_submit_button("Reopen", use_container_width=True)
        if close or reopen:
            cs.set_edge_available(p, eid, bool(reopen), reason)
            st.rerun()

with st.expander("Reset all demo data"):
    st.caption("Deletes all requests, events and routes and rebuilds the synthetic dataset.")
    if st.checkbox("I understand this deletes all demo activity") and st.button("Reset demo data", type="primary"):
        build_db.build(reset=True)
        st.success("Demo data rebuilt.")

st.markdown("#### Audit log")
log = cs.audit_log(p, 80)
st.dataframe(pd.DataFrame([{"Time": local_time(a["created_at"], "%H:%M:%S"), "Actor": a["actor"],
                            "Action": a["action"], "Detail": a["detail"]} for a in log]),
             use_container_width=True, hide_index=True)
