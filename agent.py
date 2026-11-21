"""SkyAssist agent — orchestrates LLM (language) and CODE (facts, maths, policy, approvals).
Every step is written to the `trace` table tagged LLM / CODE / HUMAN so the split is visible.

v2 additions
  * intents: STATUS ("has my assistance been approved?"), DESK ("nearest assistance desk?"), LATE
  * requests are idempotent per booking (no duplicate requests from chat + portal)
  * one shared continuation helper resumes the agent after a coordinator decision, for chat- and
    portal-created requests alike
  * approval ≠ dispatch: the agent never says staff are coming unless a dispatch update exists
"""
import asyncio
import json

import llm
import tools
from approval import ApprovalEngine
from db import connect, fmt, to_min
from services import request_store
from services.request_store import ACTION_TEXT, describe
from services.routing_engine import NoRouteError, get_engine as get_router, profile_for

MODE_TEXT = {"CART": "a priority mobility cart", "ESCORT": "a staff escort", "SELF": "no help"}


def log(conv_id, actor, step, detail=None):
    con = connect()
    con.execute("INSERT INTO trace(conv_id,actor,step,detail) VALUES(?,?,?,?)",
                (conv_id, actor, step, json.dumps(detail, default=str) if detail is not None else None))
    con.commit()
    con.close()


def say(conv_id, role, text):
    con = connect()
    con.execute("INSERT INTO messages(conv_id,role,text) VALUES(?,?,?)", (conv_id, role, text))
    con.commit()
    con.close()


def resume_message(d, actions, decision, inbound, outbound):
    """Truthful wording after a human decision. Approval is not dispatch."""
    if d["status"] == "APPROVED":
        msg = f"✅ APPROVED by {d['staff']}: {describe(actions)}."
        hold = int(d.get("hold_minutes") or 0)
        if "GATE_HOLD_UP_TO_10_MIN" in actions:
            if hold:
                new_close = fmt(to_min(outbound["boarding_close"]) + hold)
                msg += f" Gate {outbound['gate']} boarding hold approved: up to {hold} min (until {new_close} at the latest)."
            else:
                msg += " The gate hold itself was not approved."
        if decision == "MISSED_REBOOK":
            msg += f" Please wait near the aircraft door at gate {inbound['gate']}; you will be taken to the Transfer Desk once staff are dispatched."
        else:
            msg += f" Please stay at the door of {inbound['flight_no']} at gate {inbound['gate']}."
        msg += " Staff dispatch is not confirmed yet; you will get an update when it is."
        if d.get("note"):
            msg += f" Note from the coordinator: {d['note']}"
    else:
        msg = (f"❌ Your assistance request was not approved ({d.get('note') or 'no reason given'}). "
               f"No staff are on the way. Please go straight to the Transfer Desk at the Concourse "
               f"{inbound['gate'][0]} hub, or ask cabin crew at the aircraft door, so they can arrange help.")
    return msg


def schedule_continuation(engine: ApprovalEngine, req_id, conv_id, actions, decision, inbound, outbound,
                          lang="en", polish=False):
    """Run the agent's paused continuation on the approval loop: await the human, then resume."""

    def on_interim(rid):
        say(conv_id, "assistant", f"Still waiting for the coordinator to approve {rid}. Nothing is confirmed "
                                  f"yet; it has been escalated.")

    async def continuation():
        d = await engine.wait(req_id, on_interim)
        await asyncio.to_thread(_resume, conv_id, d, actions, decision, inbound, outbound, lang, polish)

    return engine.run_continuation(continuation())


def _resume(conv_id, d, actions, decision, inbound, outbound, lang, polish):
    log(conv_id, "HUMAN", f"Coordinator {d['staff']} {d['status']} {d['request_id']}", d)
    log(conv_id, "CODE", "Agent resumed from await", {"request_id": d["request_id"]})
    msg = resume_message(d, actions, decision, inbound, outbound)
    if polish:
        text, backend, why = llm.polish_reply(msg, lang, pending=False)
        log(conv_id, "LLM" if not why.startswith("skipped") else "CODE", f"Rewrite reply ({backend})", {"guard": why})
        msg = text
    say(conv_id, "assistant", msg)


class Agent:
    def __init__(self, engine: ApprovalEngine, polish: bool = True):
        self.engine = engine
        self.polish = polish

    log = staticmethod(log)
    say = staticmethod(say)

    def reply(self, conv_id, draft, language, pending=False):
        if self.polish:
            text, backend, why = llm.polish_reply(draft, language, pending)
            if why.startswith("skipped"):
                self.log(conv_id, "CODE", "Send verified draft (LLM offline)", None)
            else:
                self.log(conv_id, "LLM", f"Rewrite reply for passenger ({backend})", {"guard": why})
            if why.startswith("rejected"):
                self.log(conv_id, "CODE", "Hallucination guard blocked LLM text → sent verified draft", {"reason": why})
        else:
            text = draft
        self.say(conv_id, "assistant", text)
        return text

    # ------------------------------------------------------------ intents answered straight from the backend
    def _status_reply(self, conv_id, booking_ref, lang):
        req = request_store.latest_for_booking(booking_ref) if booking_ref else None
        self.log(conv_id, "CODE", "Read assistance request status (SQLite)", {"request": req and req["id"]})
        if not req:
            draft = "You have no assistance request on file. If you need help, ask me or use the Assistance tab."
        elif req["status"] == "PENDING":
            draft = (f"Your request {req['id']} ({describe(req['actions_list'])}) is PENDING coordinator approval. "
                     f"It is NOT confirmed yet and no staff dispatch has been confirmed.")
            if req["escalated_at"]:
                draft += " It has been escalated because it is taking longer than expected."
        elif req["status"] == "DECLINED":
            draft = (f"Your request {req['id']} was DECLINED by {req['resolved_by']}. No staff are on the way. "
                     f"Please go to the nearest Transfer Desk.")
        else:
            ds = req["dispatch_status"] or "NONE"
            draft = f"Your request {req['id']} was APPROVED by {req['resolved_by']}."
            draft += {"NONE": " Staff have not been assigned or dispatched yet.",
                      "ASSIGNED": " Staff/equipment are assigned; dispatch is not confirmed yet.",
                      "DISPATCHED": " The coordinator has confirmed dispatch.",
                      "EN_ROUTE": " Staff are on their way to you (operational update).",
                      "COMPLETED": " The assistance has been completed."}[ds]
        self.reply(conv_id, draft, lang)
        return {"decision": "STATUS"}

    def _desk_reply(self, conv_id, origin_gate, needs, lang):
        prof = profile_for(needs)
        try:
            r = get_router().nearest(origin_gate, ("TRANSFER_DESK", "ASSISTANCE_POINT"), prof)
        except NoRouteError as e:
            self.reply(conv_id, f"{e} Please ask the nearest airline or airport staff member.", lang)
            return {"decision": "NO_ROUTE"}
        name = get_router().nodes[r.destination]["name"]
        self.log(conv_id, "CODE", "Nearest assistance point (routing engine)", {"to": name, "m": r.distance_m})
        steps = "\n".join(f"{s.index}. {s.text}" for s in r.steps)
        draft = f"The nearest help point is {name}, {int(r.distance_m)} m from gate {origin_gate}.\n{steps}"
        self.reply(conv_id, draft, lang)
        return {"decision": "DESK"}

    # ------------------------------------------------------------ main entry
    def handle(self, conv_id, text, booking_ref=None, now="10:00"):
        self.say(conv_id, "user", text)
        parsed, backend = llm.parse_message(text)
        self.log(conv_id, "LLM", f"Parse passenger message ({backend})", parsed)
        lang = parsed.get("language", "en")
        intent = parsed.get("intent", "JOURNEY")

        manifest = tools.get_passenger_manifest(booking_ref) if booking_ref else None
        if manifest:
            self.log(conv_id, "CODE", "Load mobility-assistance manifest", manifest)
        if intent == "STATUS" and booking_ref:
            return self._status_reply(conv_id, booking_ref, lang)

        flights = list(parsed["flights"])
        if manifest:
            extra = [f for f in (manifest["inbound"], manifest["outbound"]) if f and f not in flights]
            if extra:
                self.log(conv_id, "CODE", "Fill missing flights from booking", {"added": extra})
            flights += extra
        statuses = {}
        for f in flights:
            s = tools.get_flight_and_gate_status(f)
            statuses[f] = s
            self.log(conv_id, "CODE", f"get_flight_and_gate_status('{f}')", s)
        inbound = next((s for s in statuses.values() if s["found"] and s["direction"] == "ARRIVAL"), None)
        outbound = next((s for s in statuses.values() if s["found"] and s["direction"] == "DEPARTURE"), None)
        unknown = [f for f, s in statuses.items() if not s["found"]]
        needs = sorted(set(parsed["needs"]) | set(manifest["needs"] if manifest else []))

        if intent == "DESK" and inbound:
            return self._desk_reply(conv_id, inbound["gate"], needs, lang)

        if unknown and not outbound:
            self.log(conv_id, "CODE", "Flight not in live data → refuse to guess", {"unknown": unknown})
            draft = (f"I can't find flight {', '.join(unknown)} in today's live flight data, so I will not guess "
                     f"its gate or time. Please check the flight number on your boarding pass, or show the pass "
                     f"at the nearest Transfer Desk (at every concourse hub).")
            if inbound:
                draft = f"I can see your arrival {inbound['flight_no']} at gate {inbound['gate']}. " + draft
            self.reply(conv_id, draft, lang)
            return {"decision": "FLIGHT_NOT_FOUND"}
        if not inbound or not outbound:
            draft = ("To work out your connection I need both flight numbers (the one you arrived on and the "
                     "one you are connecting to). They are printed on your boarding passes.")
            self.reply(conv_id, draft, lang)
            return {"decision": "NEED_INFO"}

        self.log(conv_id, "CODE", "Priority floor: merge needs (message ∪ manifest)", {"needs": needs})
        head = (f"I checked live flight data: {inbound['flight_no']} is parked at gate {inbound['gate']}. "
                f"Your connection {outbound['flight_no']} to {outbound['destination']}")

        if outbound["status"] == "CANCELLED":
            conc = inbound["gate"][0]
            self.log(conv_id, "CODE", "Connection cancelled → redirect to Transfer Desk", {"flight": outbound["flight_no"]})
            draft = (f"{head} is shown as CANCELLED. Please go to the Transfer Desk at the Concourse {conc} hub "
                     f"({tools._gate(inbound['gate'])['metres_from_hub'] + 20} m from your gate) for rebooking. "
                     f"I will not suggest a new flight myself; the desk will confirm your options.")
            self.reply(conv_id, draft, lang)
            return {"decision": "CANCELLED_REDIRECT"}

        gate_note = ""
        claimed = tools.normalize_gate(parsed.get("claimed_gate"))
        if outbound.get("previous_gate"):
            gate_note += f" now departs from gate {outbound['gate']} (changed from {outbound['previous_gate']})."
        else:
            gate_note += f" departs from gate {outbound['gate']}."
        if outbound["status"] == "DELAYED":
            gate_note += f" It is DELAYED: new departure {outbound['est']}."
        if claimed and claimed != outbound["gate"]:
            self.log(conv_id, "CODE", "Gate mismatch: passenger vs telemetry",
                     {"passenger_said": claimed, "telemetry": outbound["gate"]})
            gate_note += f" Please do NOT go to {claimed}: that gate is out of date."

        minutes_left = tools.minutes_until(outbound["boarding_close"], now)
        try:
            plan = tools.decide_assistance(needs, inbound["gate"], outbound["gate"], minutes_left)
        except NoRouteError as e:
            self.log(conv_id, "CODE", "Routing engine: no verifiable route", {"error": str(e)})
            self.reply(conv_id, f"{head}{gate_note} {e} Please go to the Transfer Desk or Special Assistance point "
                                f"at the Concourse {inbound['gate'][0]} hub so staff can help you.", lang)
            return {"decision": "NO_ROUTE"}
        self.log(conv_id, "CODE", "calculate_terminal_transfer_time(SELF)", plan["self"])
        if plan["plan"]["mode"] != "SELF":
            self.log(conv_id, "CODE", f"calculate_terminal_transfer_time({plan['plan']['mode']})", plan["plan"])
        self.log(conv_id, "CODE", "decide_assistance() policy",
                 {k: plan[k] for k in ("decision", "verdict", "actions", "minutes_left", "slack_self", "slack")})

        steps = "\n".join(f"{i}. {leg}" for i, leg in enumerate(plan["plan"]["route"], 1))
        timing = (f" Boarding closes at {outbound['boarding_close']}, which is {minutes_left} min from now "
                  f"(terminal clock {now}).")
        s, p = plan["self"], plan["plan"]
        if p["mode"] == "SELF":
            calc = (f" On foot the transfer takes about {s['total_min']} min including a {s['safety_buffer_min']} min "
                    f"safety buffer, leaving {plan['slack']} min spare.")
        else:
            calc = (f" On your own it would take about {s['total_min']} min. With {MODE_TEXT[p['mode']]} it takes about "
                    f"{p['total_min']} min including a {p['safety_buffer_min']} min safety buffer, leaving "
                    f"{plan['slack']} min.")
        draft = head + gate_note + timing + calc
        late_tip = ("\n\nIf you are running late: keep following the route, tell any staff member your flight "
                    "number, and do not assume the gate will wait — only a coordinator can approve a hold.")

        decision = plan["decision"]
        if decision == "SELF_GUIDED":
            draft += f"\nYour route:\n{steps}" + (late_tip if intent == "LATE" else "")
            self.reply(conv_id, draft, lang)
            return {"decision": decision, "plan": plan}

        if decision == "MISSED_REBOOK":
            draft = (head + gate_note + timing +
                     f" Even with a mobility cart the transfer needs about {p['total_min']} min, more than the time left "
                     f"plus the maximum {tools.MAX_GATE_HOLD_MIN} min gate hold. I'm being honest: this connection cannot "
                     f"be made safely. Please go to the Transfer Desk at the Concourse {inbound['gate'][0]} hub for rebooking.")
            if not plan["actions"]:
                self.reply(conv_id, draft, lang)
                return {"decision": decision, "plan": plan}
        else:
            draft += f"\nRoute once assistance arrives:\n{steps}"

        # -------- physical help -> durable request + async human approval, never promised by the agent
        context = build_context(inbound, outbound, now, minutes_left, needs, plan, manifest)
        req_id, created = self.engine.stage_ex(conv_id, booking_ref, plan["actions"], decision, context)
        if created:
            schedule_continuation(self.engine, req_id, conv_id, plan["actions"], decision, inbound, outbound,
                                  lang, self.polish)
            self.log(conv_id, "CODE", f"request_mobility_dispatch_async() → {req_id} PENDING · agent paused (await)",
                     {"actions": plan["actions"]})
            draft += (f"\n\nI have REQUESTED: {describe(plan['actions'])}. A terminal coordinator must approve this. "
                      f"It is NOT confirmed yet. Please stay at the aircraft door. I'll message you the moment they reply.")
        else:
            existing = request_store.get(req_id)
            self.log(conv_id, "CODE", f"Existing request {req_id} reused (no duplicate)", {"status": existing["status"]})
            draft += (f"\n\nYour assistance request {req_id} already exists and is {existing['status']}. "
                      + ("It is NOT confirmed yet." if existing["status"] == "PENDING" else
                         "See the Assistance tab for its latest status."))
        if intent == "LATE":
            draft += late_tip
        self.reply(conv_id, draft, lang, pending=True)
        return {"decision": decision, "plan": plan, "request_id": req_id, "created": created}


def build_context(inbound, outbound, now, minutes_left, needs, plan, manifest):
    p = plan["plan"]
    return {"inbound": inbound["flight_no"], "arr_gate": inbound["gate"], "outbound": outbound["flight_no"],
            "dep_gate": outbound["gate"], "boarding_close": outbound["boarding_close"], "now": now,
            "minutes_left": minutes_left, "needs": needs, "slack": plan["slack"], "slack_self": plan["slack_self"],
            "self_min": plan["self"]["total_min"], "transfer_min": p["total_min"], "transfer_mode": p["mode"],
            "verdict": plan["verdict"], "decision": plan["decision"],
            "party": (manifest["lead_name"] + f" ({manifest['party_size']} pax)") if manifest else "walk-up",
            "party_size": manifest["party_size"] if manifest else 1}
