"""/passenger — mobile-first passenger portal. Reads only the signed-in passenger's own booking."""
import streamlit as st

import tools
from agent import Agent
from approval import get_engine
from components import ui
from components.airport_map import LEGEND_HTML, render_map
from components.session import require_login, sign_out
from db import local_time, query
from services import assistance_service, navigation_service, passenger_service, request_store
from services.auth_service import PASSENGER
from services.location_provider import ManualLocationProvider
from services.routing_engine import RoutingEngine

ui.inject(ui.PASSENGER_CSS)
p = require_login(PASSENGER, "Find your next flight", "Sign in with your booking reference.",
                  ["Bookings `PNR1A2` (S1 wheelchair family), `PNR3C4`, `PNR9J1`, … password `demo123` "
                   "(or `PASSENGER_DEMO_PASSWORD`)"])
ref = p.booking_ref
ss = st.session_state


def journey(auto=True):
    return passenger_service.get_journey(p, ref, auto_request=auto)


# ------------------------------------------------------------------------------------------- header
j0 = journey()
top_l, top_r = st.columns([5, 1])
with top_l:
    ui.md(f'<div class="sa-hero"><div class="sub">SkyAssist · Booking {ui.esc(ref)}</div>'
          f'<h1>Welcome, {ui.esc(j0.get("passenger"))}</h1>'
          f'<div class="sub">Terminal clock {ui.esc(j0.get("now"))} (simulated) · synthetic demo data · '
          f'party of {ui.esc(j0.get("party_size"))}</div></div>')
with top_r:
    st.write("")
    if st.button("Sign out", use_container_width=True):
        sign_out(PASSENGER)
        st.rerun()


@st.fragment(run_every=4)
def overview():
    j = journey()
    if j["state"] != "OK":
        ui.md(ui.card(f'<div class="sa-label">Your connection</div><div style="font-size:18px;font-weight:700;'
                      f'color:#b91c1c;margin-top:4px">{ui.esc(j.get("message"))}</div>'))
        ui.md(ui.assistance_card(j["assistance"]))
        return
    out, plan = j["outbound"], j["plan"]
    sub = (f"Without assistance: {ui.RISK_LABEL[j['risk_self']]} · with the requested assistance: "
           f"{ui.RISK_LABEL[j['risk_assisted']]}" if plan["actions"] else "")
    ui.md(ui.risk_banner(j["risk"], j["messages"][-1], sub))
    ui.md(ui.gate_card(out["gate"], j.get("gate_changed_from"), out["flight_no"], out["destination"],
                       out["boarding_close"], out["status"]))
    st.write("")
    eta = plan["plan"]["total_min"] if j["assistance"]["state"] in ("APPROVED", "DISPATCHED", "STAFF EN ROUTE") \
        else plan["self"]["total_min"]
    ui.tiles([("Time remaining", f"{j['minutes_left']} min", f"boarding closes {out['boarding_close']}"),
              ("Transfer estimate", f"{eta} min", "incl. screening & safety buffer"),
              ("Distance", f"{plan['self']['metres']:,} m", plan["self"]["route_profile"].replace("_", "-").lower() + " route")])
    for m in j["messages"][:-1]:
        st.markdown(f"- {m}")
    ui.md(ui.assistance_card(j["assistance"]))
    notes = request_store.notifications(ref, 3)
    if notes:
        ui.md(ui.card("".join(f'<div style="padding:4px 0"><span class="sa-muted">{local_time(n["created_at"])}</span> · '
                              f'{ui.esc(n["message"])}</div>' for n in notes), "background:#f8fafc"))


overview()

tab_nav, tab_fl, tab_as, tab_chat = st.tabs(["🧭  Navigate", "✈️  Flights", "🛟  Assistance", "💬  Ask SkyAssist"])

# ------------------------------------------------------------------------------------------- navigation
with tab_nav:
    @st.fragment(run_every=5)
    def navigation():
        j = journey(auto=False)
        rr = j.get("route_result")
        if not rr:
            st.info(j.get("message", "No route available."))
            return
        loc = rr["location"]
        ui.md(f'<div class="sa-muted">Starting point: <b>{ui.esc(loc["label"])}</b> · '
              f'{"set manually" if loc["source"] == "MANUAL" else "known arrival gate"} · '
              f'<b>not live-tracked</b> (no indoor positioning connected)</div>')
        if rr.get("error"):
            st.error(f"🚫 {rr['error']}")
            st.warning("We will not show an unverified route. Please go to the nearest Special Assistance point or "
                       "Transfer Desk, or ask any airport staff member.")
            return
        route = rr["route"]
        if rr.get("recalculated") and rr.get("reason"):
            st.warning(f"🔄 {rr['reason']}")
        if route["profile"] in ("STEP_FREE", "CART"):
            st.success("♿ Step-free route verified: lifts instead of escalators, no stairs.")
        steps = route["steps"]
        prog = rr["progress"]
        started = bool(prog.get("started"))
        cur = int(prog.get("step_index") or 0) if started else None
        needs = j.get("needs", [])
        speed_key = min([n for n in needs if n in tools.SPEED] + ["WALK"], key=lambda k: tools.SPEED[k])
        speed = tools.SPEED[speed_key]
        remaining = sum(s["distance_m"] for s in steps[(cur or 0):])
        eng = RoutingEngine()
        dest_name = eng.nodes[route["node_path"][-1]]["name"]

        # instructions first (mobile-first), full-width map below
        if not started:
            ui.md(ui.card(f'<div class="sa-label">Destination</div><div class="sa-big">{ui.esc(dest_name)}</div>'
                          f'<div class="sa-muted">{len(steps)} steps · {int(route["distance_m"]):,} m · about '
                          f'{round(route["distance_m"] / speed)} min walking at {speed} m/min</div>'))
            if st.button("▶  Start navigation", type="primary", use_container_width=True, key="nav_start"):
                navigation_service.start(ref)
                st.rerun(scope="fragment")
        else:
            s = steps[cur]
            last = cur == len(steps) - 1
            ui.md(ui.card(f'<div class="sa-label">Step {cur + 1} of {len(steps)} · next instruction</div>'
                          f'<div style="font-size:22px;font-weight:800;color:#0b2545;margin:6px 0 10px">{ui.esc(s["text"])}</div>'
                          f'<div style="display:flex;gap:26px;flex-wrap:wrap"><div><div class="sa-label">Distance left</div>'
                          f'<div class="sa-big" style="font-size:24px">{int(remaining):,} m</div></div>'
                          f'<div><div class="sa-label">Walking time left</div><div class="sa-big" style="font-size:24px">'
                          f'{round(remaining / speed)} min</div></div><div><div class="sa-label">Destination</div>'
                          f'<div class="sa-big" style="font-size:24px">{ui.esc(dest_name)}</div></div></div>'
                          + (f'<div style="margin-top:10px;color:#15803d;font-weight:700">You have arrived. Check the gate '
                             f'screen shows {ui.esc(j["outbound"].get("flight_no", ""))}.</div>' if last else ""),
                          "border:2px solid #f59e0b"))
            b1, b2 = st.columns(2)
            if b1.button("◀  Previous step", use_container_width=True, disabled=cur == 0, key="nav_prev"):
                navigation_service.move(ref, -1, len(steps))
                st.rerun(scope="fragment")
            if b2.button("✓  Mark step completed", type="primary", use_container_width=True, disabled=last,
                         key="nav_next"):
                navigation_service.move(ref, 1, len(steps))
                st.rerun(scope="fragment")
        r1, r2 = st.columns(2)
        if r1.button("🔄  Recalculate route", use_container_width=True, key="nav_recalc"):
            navigation_service.force_recalculate(ref)
            st.rerun(scope="fragment")
        ss["nav_full"] = r2.toggle("View full route", value=ss.get("nav_full", not started), key="nav_full_t")
        ui.md(f'<div class="sa-label" style="margin:10px 0 4px">Map · your route to {ui.esc(dest_name)} · '
              f'{int(route["distance_m"]):,} m</div>')
        ui.md(render_map(list(eng.nodes.values()), list(eng.edges.values()), route, cur, title=dest_name))
        ui.md(LEGEND_HTML)
        with st.expander("📍 Update my current location (manual)"):
            st.caption("Choose where you are now. SkyAssist does not track your position.")
            opts = [n["node_id"] for n in sorted(
                [n for n in eng.nodes.values() if n["node_type"] in ("GATE", "HUB", "TRANSFER_DESK")],
                key=lambda n: (n["concourse"], n["node_type"] != "HUB", n["name"]))]
            choice = st.selectbox("I am at", opts, format_func=lambda nid: eng.nodes[nid]["name"], key="nav_loc",
                                  index=opts.index(loc["node_id"]) if loc["node_id"] in opts else 0)
            l1, l2 = st.columns(2)
            if l1.button("Set location", use_container_width=True, key="nav_setloc"):
                ManualLocationProvider.set_manual(ref, choice)
                st.rerun(scope="fragment")
            if l2.button("Reset to arrival gate", use_container_width=True, key="nav_resetloc"):
                ManualLocationProvider.clear_manual(ref)
                st.rerun(scope="fragment")
        if ss.get("nav_full") or not started:
            ui.md(ui.card(f'<div class="sa-label">Your route to {ui.esc(dest_name)}</div>' + ui.steps_list(steps, cur)))

    navigation()

# ------------------------------------------------------------------------------------------- flights
with tab_fl:
    j = journey(auto=False)
    if j.get("inbound", {}).get("found"):
        i = j["inbound"]
        ui.md(ui.flight_card("Arriving flight", i, [("From", ui.esc(i["origin"])), ("Arrival gate", ui.esc(i["gate"])),
                                                    ("Arrived", ui.esc(i.get("est")))]))
    if j.get("outbound", {}).get("found"):
        o = j["outbound"]
        rows = [("To", ui.esc(o["destination"])), ("Departure gate", f'<b style="font-size:18px">{ui.esc(o["gate"])}</b>')]
        if o.get("previous_gate"):
            rows.append(("Previous gate", f'<s>{ui.esc(o["previous_gate"])}</s> — do not go there'))
        rows += [("Boarding closes", ui.esc(o.get("boarding_close") or "—")), ("Departure", ui.esc(o.get("est") or o.get("sched")))]
        ui.md(ui.flight_card("Connecting flight", o, rows))
    else:
        st.info(j.get("message", "No verified connecting flight."))
    st.caption("Flight data source: synthetic demonstration dataset (no live airport feed connected).")

# ------------------------------------------------------------------------------------------- assistance
with tab_as:
    @st.fragment(run_every=4)
    def assistance():
        j = journey(auto=False)
        view = j["assistance"]
        ui.md(ui.assistance_card(view))
        if view.get("request"):
            ui.md(ui.card('<div class="sa-label">Request history</div>' +
                          ui.timeline([e for e in request_store.events(view["request"]["id"])
                                       if e["event_type"] != "PASSENGER_NOTIFIED"])))
        active = view.get("request") and (view["request"]["status"] == "PENDING" or
                                          (view["request"]["status"] == "APPROVED" and
                                           view["request"]["dispatch_status"] != "COMPLETED"))
        if not active and j.get("state") == "OK":
            with st.form("ask_help"):
                st.markdown("**Request physical assistance**")
                items = st.multiselect("What do you need?", assistance_service.PASSENGER_SELECTABLE,
                                       format_func=lambda a: request_store.ACTION_TEXT[a])
                note = st.text_input("Anything the coordinator should know? (optional)")
                if st.form_submit_button("Send request to coordinator", type="primary", use_container_width=True):
                    try:
                        rid, _ = assistance_service.passenger_request(p, ref, items, note, j)
                        st.success(f"Request {rid} sent. It is not confirmed until a coordinator approves it.")
                        st.rerun(scope="fragment")
                    except ValueError as e:
                        st.error(str(e))
        notes = request_store.notifications(ref, 20)
        if notes:
            st.markdown("**Updates**")
            for n in notes:
                st.markdown(f"`{local_time(n['created_at'])}` {n['message']}")

    assistance()

# ------------------------------------------------------------------------------------------- chat
with tab_chat:
    conv = assistance_service.chat_conv(ref)
    st.caption("SkyAssist answers from your booking, live gate data and the routing engine. It never invents "
               "gates, times, routes or approvals. English and Hinglish supported.")
    quick = ["Where is my next gate?", "How long will it take?", "Can I make my connection?",
             "Has my assistance been approved?", "Where is the nearest assistance desk?", "I am running late, what should I do?"]
    qc = st.columns(3)
    asked = None
    for k, q in enumerate(quick):
        if qc[k % 3].button(q, use_container_width=True, key=f"q{k}"):
            asked = q
    with st.form("chat", clear_on_submit=True):
        typed = st.text_input("Ask a question", placeholder="e.g. Dadi ko wheelchair chahiye, gate kahan hai?")
        if st.form_submit_button("Send", use_container_width=True) and typed.strip():
            asked = typed.strip()
    if asked:
        with st.spinner("Checking live data…"):
            Agent(get_engine(), polish=True).handle(conv, asked, ref, passenger_service.demo_clock(ref))

    @st.fragment(run_every=3)
    def chat_log():
        msgs = query("SELECT role, text FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT 30", (conv,))
        if not msgs:
            st.caption("No messages yet.")
        for m in msgs:
            with st.chat_message("user" if m["role"] == "user" else "assistant",
                                 avatar="🧳" if m["role"] == "user" else "🛫"):
                st.markdown(m["text"].replace("\n", "  \n"))

    chat_log()
