"""PASSENGER SERVICE — everything the passenger portal shows, computed by deterministic code.

`get_journey()` is the single source for the passenger screen: flights, verified gates, time left,
transfer estimates, risk, route and assistance status. Every number comes from tools.py / the routing
engine / SQLite. The text is generated from those numbers, never by an LLM.
"""
import json
import os

import tools
from db import query_one
from services import assistance_service, navigation_service
from services.auth_service import Principal, require_booking_access
from services.integrations import SYNTHETIC
from services.location_provider import get_location_provider
from services.routing_engine import NoRouteError, profile_for

RISK_COPY = {
    "COMFORTABLE": "Your connection is comfortable.",
    "TIGHT": "Your connection is tight.",
    "AT_RISK": "Your connection is at risk.",
}


def demo_clock(booking_ref):
    """Simulated terminal clock for the synthetic dataset (honestly labelled in the UI)."""
    env = os.getenv("DEMO_CLOCK")
    if env:
        return env
    row = query_one("SELECT now FROM scenarios WHERE booking_ref=?", (booking_ref,))
    return row["now"] if row else "10:00"


def get_journey(principal: Principal, booking_ref: str, auto_request: bool = True) -> dict:
    require_booking_access(principal, booking_ref)
    manifest = tools.get_passenger_manifest(booking_ref)
    if not manifest:
        return {"state": "NO_BOOKING", "message": "We could not find this booking."}
    now = demo_clock(booking_ref)
    j = {"booking_ref": booking_ref, "passenger": manifest["lead_name"], "party_size": manifest["party_size"],
         "needs": manifest["needs"], "now": now, "data_source": SYNTHETIC, "messages": []}
    inbound = tools.get_flight_and_gate_status(manifest["inbound"]) if manifest["inbound"] else {"found": False}
    outbound = tools.get_flight_and_gate_status(manifest["outbound"]) if manifest["outbound"] else {"found": False}
    j["inbound"], j["outbound"] = inbound, outbound
    j["assistance"] = assistance_service.passenger_view(booking_ref)

    if not inbound.get("found"):
        j.update(state="NO_INBOUND", message="We cannot find your arriving flight in the flight data.")
        return j
    if not outbound.get("found"):
        j.update(state="NO_CONNECTION",
                 message="We cannot find a verified connecting flight on this booking, so we will not guess a gate. "
                         "Please check your boarding pass or visit a Transfer Desk.")
        return j
    if outbound["status"] == "CANCELLED":
        j.update(state="CANCELLED",
                 message=f"Your connecting flight {outbound['flight_no']} is cancelled. Please go to the Transfer "
                         f"Desk at the Concourse {inbound['gate'][0]} hub for rebooking.")
        j["route_result"] = _route(booking_ref, inbound["gate"], f"TD_{inbound['gate'][0]}", manifest["needs"],
                                   desk=True)
        return j

    minutes_left = tools.minutes_until(outbound["boarding_close"], now)
    try:
        plan = tools.decide_assistance(manifest["needs"], inbound["gate"], outbound["gate"], minutes_left)
    except NoRouteError as e:
        j.update(state="NO_ROUTE", message=str(e), minutes_left=minutes_left, dest_gate=outbound["gate"])
        fix = get_location_provider().current(booking_ref, inbound["gate"])
        j["route_result"] = {"route": None, "error": str(e), "location": fix.__dict__,
                             "profile": profile_for(manifest["needs"]),
                             "progress": navigation_service.progress(booking_ref)}
        return j

    j.update(state="OK", plan=plan, minutes_left=minutes_left, dest_gate=outbound["gate"],
             gate_changed_from=outbound.get("previous_gate"))
    if auto_request and plan["actions"] and not j["assistance"]["request"]:
        assistance_service.request_from_policy(booking_ref, manifest, inbound, outbound, now, minutes_left, plan)
        j["assistance"] = assistance_service.passenger_view(booking_ref)
    # Honest risk: until assistance is APPROVED the passenger is effectively on their own.
    req = j["assistance"]["request"]
    assisted_confirmed = bool(req and req["status"] == "APPROVED")
    self_verdict = verdict(plan["slack_self"])
    j["risk"] = plan["verdict"] if assisted_confirmed else self_verdict
    j["risk_self"], j["risk_assisted"] = self_verdict, plan["verdict"]

    m = j["messages"]
    m.append(f"Your next flight {outbound['flight_no']} to {outbound['destination']} departs from Gate "
             f"{outbound['gate']}." + (f" The gate changed from {outbound['previous_gate']}."
                                       if outbound.get("previous_gate") else ""))
    if outbound["status"] == "DELAYED":
        m.append(f"Your flight is delayed: new departure {outbound['est']}.")
    m.append(f"You have {minutes_left} minutes before boarding closes at {outbound['boarding_close']}.")
    if plan["plan"]["mode"] == "SELF":
        m.append(f"Estimated transfer time: {plan['self']['total_min']} minutes, including a "
                 f"{plan['self']['safety_buffer_min']}-minute safety buffer.")
    else:
        m.append(f"Estimated transfer time: {plan['self']['total_min']} minutes on your own, "
                 f"{plan['plan']['total_min']} minutes with {_mode(plan['plan']['mode'])}.")
    status_line = RISK_COPY[j["risk"]]
    if plan["actions"]:
        status_line += {"PENDING": " Assistance has been requested and is waiting for coordinator approval.",
                        "APPROVED": " Assistance has been approved.",
                        "DECLINED": " Assistance was not approved."}.get(req["status"] if req else "", "")
    m.append(status_line)
    if plan["decision"] == "MISSED_REBOOK":
        m.append("Even with assistance this connection cannot be made safely. Please go to the Transfer Desk "
                 "for rebooking.")

    j["route_result"] = _route(booking_ref, inbound["gate"], outbound["gate"], manifest["needs"])
    return j


def _route(booking_ref, arrival_gate, dest, needs, desk=False):
    fix = get_location_provider().current(booking_ref, arrival_gate)
    prof = profile_for(needs)
    res = navigation_service.current_route(booking_ref, fix.node_id, dest if desk else dest, prof)
    res["location"] = fix.__dict__
    res["profile"] = prof
    res["progress"] = navigation_service.progress(booking_ref)
    return res


def verdict(slack):
    return "COMFORTABLE" if slack >= 10 else ("TIGHT" if slack >= 0 else "AT_RISK")


def _mode(mode):
    return {"CART": "a priority mobility cart", "ESCORT": "a staff escort"}.get(mode, "assistance")
