"""/coordinator — desktop-first airport operations dashboard for assistance requests."""
import json

import pandas as pd
import streamlit as st

from components import ui
from components.airport_map import LEGEND_HTML, render_map
from components.session import nav_link, require_login, sign_out
from db import local_time
from services import coordinator_service as cs
from services.auth_service import COORDINATOR
from services.request_store import ACTION_TEXT, MAX_GATE_HOLD_MIN, StateConflict, describe
from services.routing_engine import RoutingEngine

ui.inject(ui.COORDINATOR_CSS)
p = require_login(COORDINATOR, "Operations sign-in", "Airport terminal coordinators only.",
                  ["`sarah` / `aisha`, password `coord123` (or `COORDINATOR_DEMO_PASSWORD`)"])
ss = st.session_state

STATUS_FILTERS = ["PENDING", "ESCALATED", "APPROVED", "DECLINED"]
TAG_FILTERS = ["Wheelchair", "Escort", "Mobility cart", "Gate hold"]

with st.sidebar:
    st.markdown("### ✈️ SkyAssist Ops")
    st.caption(f"Signed in as **{p.display_name}** · coordinator")
    nav_link("views/coordinator.py", "Assistance requests", "🛟")
    nav_link("views/operations.py", "Operations overview", "📊")
    nav_link("views/occ.py", "Operations Control Centre (3.0)", "🛫")
    st.divider()
    ss["f_status"] = st.multiselect("Status", STATUS_FILTERS, default=ss.get("f_status", ["PENDING", "ESCALATED"]))
    ss["f_tags"] = st.multiselect("Assistance type", TAG_FILTERS, default=ss.get("f_tags", []))
    st.divider()
    if st.button("Sign out", use_container_width=True):
        sign_out(COORDINATOR)
        st.rerun()
    st.caption("Synthetic demonstration data. Demo sign-in, not production identity.")


def age(s):
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


ui.md('<div style="display:flex;align-items:baseline;gap:14px"><div style="font-size:26px;font-weight:800;color:#0b2545">'
      'Assistance operations</div><div class="sa-muted">Live queue · decisions are atomic and audited</div></div>')


@st.fragment(run_every=4)
def kpis():
    k = cs.kpis(p)
    cols = st.columns(7)
    for col, (label, key) in zip(cols, [("Active connections", "active_connections"), ("Pending", "pending"),
                                        ("Approved", "approved"), ("Declined", "declined"),
                                        ("Passengers at risk", "at_risk"), ("Gate holds", "gate_holds"),
                                        ("Active assignments", "active_assignments")]):
        col.markdown(ui.kpi(label, k[key]), unsafe_allow_html=True)


kpis()
st.write("")
left, right = st.columns([1, 1.75], gap="large")

with left:
    @st.fragment(run_every=4)
    def queue():
        rows = cs.list_requests(p, ss.get("f_status") or None, ss.get("f_tags") or None)
        ui.md(f'<div class="sa-label" style="margin-bottom:6px">Request queue · {len(rows)} shown · AT RISK first, '
              f'then least time remaining</div>')
        if not rows:
            ui.md(ui.empty("No requests match these filters."))
            return
        for r in rows:
            ctx = r["context_dict"]
            st_label = "ESCALATED" if r["status"] == "PENDING" and r["escalated_at"] else r["status"]
            resolved = r["status"] != "PENDING"
            ui.md(
                f'<div class="sa-req {r["risk"]} {"resolved" if resolved else ""}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;gap:6px">'
                f'<span class="id">{r["id"]}</span><span>{ui.risk_badge(r["risk"])} '
                f'{ui.badge(st_label, ui.STATE_TONE.get(st_label, "neutral"))}</span></div>'
                f'<div style="margin:4px 0;font-weight:600">{ui.esc(ctx.get("party"))} · {ui.esc(r["booking_ref"])}</div>'
                f'<div class="sa-grid"><span>✈ {ui.esc(ctx.get("inbound"))} @ {ui.esc(ctx.get("arr_gate"))} → '
                f'{ui.esc(ctx.get("outbound"))} @ <b>{ui.esc(ctx.get("dep_gate"))}</b></span>'
                f'<span>Needs: {ui.esc(", ".join(ctx.get("needs") or []) or "—")}</span>'
                f'<span>Closes {ui.esc(ctx.get("boarding_close"))} · <b>{ui.esc(r["minutes_left"])} min left</b></span>'
                f'<span>Transfer {ui.esc(ctx.get("transfer_min"))} min · spare <b>{ui.esc(ctx.get("slack"))} min</b></span>'
                f'<span>{ui.esc(", ".join(r["tags"]))}</span><span class="sa-muted">age {age(r["age_s"])}</span></div></div>')
            if st.button(f"Open {r['id']}", key=f"open_{r['id']}", use_container_width=True,
                         type="primary" if ss.get("sel_req") == r["id"] else "secondary"):
                ss["sel_req"] = r["id"]
                st.rerun()

    queue()

with right:
    sel = ss.get("sel_req")
    if not sel:
        ui.md(ui.empty("Select a request from the queue to review it."))
    else:
        d = cs.request_detail(p, sel)
        if not d:
            ui.md(ui.empty("Request not found."))
        else:
            r, ctx = d["request"], d["request"]["context_dict"]
            st_label = "ESCALATED" if r["status"] == "PENDING" and r["escalated_at"] else r["status"]
            h1, h2 = st.columns([4, 1])
            h1.markdown(f'<div style="font-size:22px;font-weight:800;color:#0b2545">{r["id"]} '
                        f'{ui.badge(st_label, ui.STATE_TONE.get(st_label, "neutral"))} {ui.risk_badge(r["risk"])} '
                        f'{ui.badge("dispatch: " + (r["dispatch_status"] or "NONE"), "info") if r["status"] == "APPROVED" else ""}'
                        f'</div><div class="sa-muted">Created {local_time(r["created_at_utc"], "%H:%M:%S")} · age {age(r["age_s"])}'
                        f' · source {ui.esc(r.get("source"))}</div>', unsafe_allow_html=True)
            if h2.button("↻ Refresh", use_container_width=True):
                st.rerun()
            if d.get("gate_changed_since_request"):
                st.warning(f"Gate changed since this request was created: now {d['outbound']['gate']} "
                           f"(request was for {ctx.get('dep_gate')}). Review the route below.")

            c1, c2 = st.columns(2)
            with c1:
                pax = d["passenger"] or {}
                ui.md(ui.card('<div class="sa-label">Passenger &amp; flights</div><table class="sa-det" style="width:100%">'
                              + "".join(f"<tr><td>{k}</td><td><b>{ui.esc(v)}</b></td></tr>" for k, v in [
                                  ("Passenger", pax.get("lead_name")), ("Booking", r["booking_ref"]),
                                  ("Party size", pax.get("party_size")), ("Needs", ", ".join(ctx.get("needs") or []) or "—"),
                                  ("Arriving", f'{ctx.get("inbound")} · gate {ctx.get("arr_gate")}'),
                                  ("Connecting", f'{ctx.get("outbound")} · gate {d["outbound"]["gate"] if d.get("outbound") else ctx.get("dep_gate")}'),
                                  ("Boarding closes", ctx.get("boarding_close")), ("Terminal clock", f'{ctx.get("now")} (simulated)')])
                              + "</table>"))
            with c2:
                ui.md('<div class="sa-calc"><div class="sa-label">Deterministic calculation (code)</div>'
                      '<table class="sa-det" style="width:100%">'
                      + "".join(f"<tr><td>{k}</td><td><b>{ui.esc(v)}</b></td></tr>" for k, v in [
                          ("Time remaining", f'{ctx.get("minutes_left")} min'),
                          ("Transfer on own", f'{ctx.get("self_min", "—")} min'),
                          (f'Transfer with {str(ctx.get("transfer_mode", "")).lower()}', f'{ctx.get("transfer_min")} min'),
                          ("Spare time (assisted)", f'{ctx.get("slack")} min'),
                          ("Spare time (on own)", f'{ctx.get("slack_self", "—")} min'),
                          ("Policy decision", ctx.get("decision")),
                          ("Requested", describe(r["actions_list"]))]) + "</table></div>")
                st.write("")
                ui.md(f'<div class="sa-ai"><div class="sa-label">Situation summary · {ui.esc(d["summary_source"])}</div>'
                      f'<div style="font-size:14px;margin-top:4px">{ui.esc(d["summary"])}</div></div>')

            route = (d.get("route") or {}).get("route")
            if route:
                eng = RoutingEngine()
                ui.md(f'<div class="sa-label" style="margin:12px 0 4px">Passenger route · {int(route["distance_m"]):,} m · '
                      f'{route["profile"].replace("_", "-").lower()} · risk {ui.RISK_LABEL[r["risk"]]}</div>')
                ui.md(render_map(list(eng.nodes.values()), list(eng.edges.values()), route, None))
                ui.md(LEGEND_HTML)
                with st.expander("Route instructions"):
                    ui.md(ui.steps_list(route["steps"]))
            elif d.get("route"):
                st.error(f"Route unavailable: {d['route']['error']}")

            # ---------------- decision controls
            sug = d["suggested"]
            staff_opts = [""] + [s["staff_id"] for s in sug["all_staff"]]
            res_opts = [""] + [x["resource_id"] for x in sug["all_resources"]]
            staff_name = {s["staff_id"]: f'{s["name"]} ({s["role"]})' for s in sug["all_staff"]}
            res_name = {x["resource_id"]: x["label"] for x in sug["all_resources"]}
            if r["status"] == "PENDING":
                st.markdown("#### Decision")
                st.caption("Suggested (available): " + (", ".join(staff_name[s["staff_id"]] for s in sug["staff"]) or "no staff")
                           + " · " + (", ".join(res_name[x["resource_id"]] for x in sug["resources"]) or "no equipment"))
                with st.form(f"decide_{r['id']}"):
                    a1, a2 = st.columns(2)
                    staff = a1.selectbox("Assign staff (optional)", staff_opts,
                                         format_func=lambda s: staff_name.get(s, "— none yet —"))
                    res = a2.selectbox("Assign mobility resource (optional)", res_opts,
                                       format_func=lambda s: res_name.get(s, "— none yet —"))
                    hold = None
                    if "GATE_HOLD_UP_TO_10_MIN" in r["actions_list"]:
                        hold = st.slider("Gate hold to approve (minutes, policy max 10)", 0, MAX_GATE_HOLD_MIN,
                                         MAX_GATE_HOLD_MIN)
                    note = st.text_area("Operational note (shown to the passenger)", placeholder="e.g. Cart #2 meeting at C12")
                    reviewed = st.checkbox("I have reviewed the passenger, flights, route, timing and requested items.")
                    b1, b2 = st.columns(2)
                    approve = b1.form_submit_button("✅ APPROVE REQUEST", type="primary", use_container_width=True)
                    decline = b2.form_submit_button("❌ DECLINE REQUEST", use_container_width=True)
                if approve or decline:
                    if not reviewed:
                        st.error("Please confirm you have reviewed the request before deciding.")
                    else:
                        try:
                            cs.decide(p, r["id"], bool(approve), note, hold, staff or None, res or None)
                            st.success(f"{r['id']} {'approved' if approve else 'declined'}. The passenger has been updated.")
                            st.rerun()
                        except StateConflict as e:
                            st.error(f"Not applied: {e}")
                        except ValueError as e:
                            st.error(str(e))
            elif r["status"] == "APPROVED" and r["dispatch_status"] != "COMPLETED":
                st.markdown("#### Dispatch")
                st.caption("Passengers only see DISPATCHED / EN ROUTE after you record it here.")
                if r["dispatch_status"] in ("NONE", "ASSIGNED"):
                    with st.form(f"assign_{r['id']}"):
                        a1, a2 = st.columns(2)
                        staff = a1.selectbox("Staff", staff_opts, format_func=lambda s: staff_name.get(s, "—"))
                        res = a2.selectbox("Mobility resource", res_opts, format_func=lambda s: res_name.get(s, "—"))
                        if st.form_submit_button("Assign", use_container_width=True):
                            try:
                                cs.assign(p, r["id"], staff or None, res or None)
                                st.rerun()
                            except (StateConflict, ValueError) as e:
                                st.error(str(e))
                nxt = {"ASSIGNED": "DISPATCHED", "DISPATCHED": "EN_ROUTE", "EN_ROUTE": "COMPLETED"}.get(r["dispatch_status"])
                if nxt and st.button(f"Mark {nxt.replace('_', ' ').lower()}", type="primary", use_container_width=True):
                    try:
                        cs.advance(p, r["id"], nxt)
                        st.rerun()
                    except StateConflict as e:
                        st.error(str(e))
                if r["dispatch_status"] == "NONE":
                    st.info("Assign staff or equipment before marking a dispatch.")

            t1, t2 = st.columns(2)
            with t1:
                st.markdown("#### Status history")
                ui.md(ui.timeline(d["events"]))
            with t2:
                st.markdown("#### Agent execution trace")
                for t in d["trace"][-14:]:
                    tag = {"LLM": "info", "CODE": "dark", "HUMAN": "good"}.get(t["actor"], "neutral")
                    ui.md(f'<div style="font-size:13px;padding:3px 0">{ui.badge(t["actor"], tag)} {ui.esc(t["step"])}</div>')
                if not d["trace"]:
                    st.caption("No agent trace for this request.")

st.divider()
st.markdown("#### Request history (all events)")
hist = cs.history(p, 60)
if hist:
    st.dataframe(pd.DataFrame([{"Time": local_time(h["created_at"], "%H:%M:%S"), "Request": h["request_id"],
                                "Booking": h["booking_ref"], "Event": h["event_type"], "By": h["actor"],
                                "Detail": h["detail"]} for h in hist]), use_container_width=True, hide_index=True)
