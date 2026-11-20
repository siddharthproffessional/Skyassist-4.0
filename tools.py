"""DETERMINISTIC TOOLS — plain Python, no LLM anywhere in this file.

  get_flight_and_gate_status()        live telemetry lookup (SQLite)
  calculate_terminal_transfer_time()  walking / wheelchair / cart maths with hard safety buffers
  decide_assistance()                 priority-floor policy: what must be dispatched, hold or rebook
  request_mobility_dispatch_async()   async human-approval tool (lives in approval.py, re-exported here)
"""
import json
import math
import re

from db import connect, to_min

# ---------- terminal physics (metres per minute) ----------
SPEED = {"WALK": 80, "STROLLER": 65, "ELDERLY": 55, "WCHR": 50, "CART": 160}
DEPLANE_MIN = {"STANDARD": 6, "WCHR_UNASSISTED": 12, "WCHR_AT_DOOR": 8}
SCREENING_MIN = {"STANDARD": 8, "FAST_TRACK": 4}
# hard safety buffers (priority floors) — the largest applicable one is used
BUFFER_MIN = {"WCHR": 10, "UMNR": 10, "ELDERLY": 5, "STROLLER": 5}
MAX_GATE_HOLD_MIN = 10
HOLD_TRIGGER_SLACK_MIN = 3
NEEDS_CODES = ["WCHR", "UMNR", "ELDERLY", "STROLLER"]


def normalize_gate(g):
    if not g:
        return None
    m = re.match(r"^\s*([ABC])\s*-?\s*(\d{1,2})\s*$", str(g).upper())
    return f"{m.group(1)}{int(m.group(2)):02d}" if m else None


# ---------------------------------------------------------------- tool 1
def get_flight_and_gate_status(flight_no: str) -> dict:
    """Return live telemetry for a flight, or found=False. Never guesses."""
    con = connect()
    row = con.execute("SELECT * FROM flights WHERE flight_no=?", (flight_no.upper(),)).fetchone()
    con.close()
    if not row:
        return {"found": False, "flight_no": flight_no.upper()}
    d = dict(row)
    d["found"] = True
    return d


def get_passenger_manifest(booking_ref: str):
    con = connect()
    row = con.execute("SELECT * FROM passengers WHERE booking_ref=?", (booking_ref,)).fetchone()
    con.close()
    if not row:
        return None
    d = dict(row)
    d["needs"] = json.loads(d["needs"])
    return d


def _gate(g):
    con = connect()
    row = con.execute("SELECT * FROM gates WHERE gate=?", (g,)).fetchone()
    con.close()
    return dict(row) if row else None


def route(from_gate: str, to_gate: str, profile: str = "STANDARD") -> dict:
    """Walking route from the shared graph routing engine (services/routing_engine.py).
    The map, the navigation screen and the transfer calculator all use this same engine,
    so distance and directions can never disagree."""
    from services.routing_engine import get_engine
    r = get_engine().shortest_path(from_gate, to_gate, profile)
    legs = [s.text for s in r.steps if s.kind not in ("START", "ARRIVE")]
    return {"metres": int(round(r.distance_m)), "legs": legs, "profile": profile,
            "accessible_verified": r.accessible_verified, "node_path": r.node_path}


# ---------------------------------------------------------------- tool 2
def calculate_terminal_transfer_time(from_gate: str, to_gate: str, needs: list, mode: str = "SELF") -> dict:
    """mode: SELF (on your own), CART (priority mobility cart), ESCORT (staff walks with you).
    Returns a full, auditable breakdown. Totals are rounded UP (never optimistic).
    Step-free routing is used for wheelchair / stroller / elderly passengers and for carts."""
    from services.routing_engine import profile_for
    needs = set(needs or [])
    r = route(from_gate, to_gate, profile_for(needs, mode))
    if mode == "CART":
        speed_key = "CART"
    else:
        speed_key = min([n for n in needs if n in SPEED] + ["WALK"], key=lambda k: SPEED[k])
    walk = r["metres"] / SPEED[speed_key]
    if "WCHR" in needs:
        deplane = DEPLANE_MIN["WCHR_AT_DOOR"] if mode != "SELF" else DEPLANE_MIN["WCHR_UNASSISTED"]
    else:
        deplane = DEPLANE_MIN["STANDARD"]
    screening = SCREENING_MIN["FAST_TRACK"] if mode != "SELF" else SCREENING_MIN["STANDARD"]
    buffer = max([BUFFER_MIN[n] for n in needs if n in BUFFER_MIN] + [0])
    total = math.ceil(deplane + walk + screening + buffer)
    return {
        "from_gate": from_gate, "to_gate": to_gate, "mode": mode, "metres": r["metres"],
        "speed_profile": speed_key, "speed_m_per_min": SPEED[speed_key],
        "deplane_min": deplane, "walk_min": round(walk, 1), "screening_min": screening,
        "safety_buffer_min": buffer, "total_min": total, "route": r["legs"],
        "route_profile": r["profile"], "accessible_verified": r["accessible_verified"],
    }


def minutes_until(close_hhmm: str, now_hhmm: str) -> int:
    return to_min(close_hhmm) - to_min(now_hhmm)


# ---------------------------------------------------------------- policy (code, not LLM)
def decide_assistance(needs: list, from_gate: str, to_gate: str, minutes_left: int) -> dict:
    needs = set(needs or [])
    self_calc = calculate_terminal_transfer_time(from_gate, to_gate, list(needs), "SELF")
    slack_self = minutes_left - self_calc["total_min"]
    actions = []
    if "UMNR" in needs:
        actions.append("STAFF_ESCORT")
    if "WCHR" in needs:
        actions += ["WHEELCHAIR_AT_DOOR", "MOBILITY_CART"]
    elif slack_self < 5 and needs & {"ELDERLY", "STROLLER"}:
        actions.append("MOBILITY_CART")
    elif slack_self < 0:
        actions.append("MOBILITY_CART")

    if "MOBILITY_CART" in actions:
        eff_calc = calculate_terminal_transfer_time(from_gate, to_gate, list(needs), "CART")
    elif "STAFF_ESCORT" in actions:
        eff_calc = calculate_terminal_transfer_time(from_gate, to_gate, list(needs), "ESCORT")
    else:
        eff_calc = self_calc
    slack = minutes_left - eff_calc["total_min"]

    if slack < -MAX_GATE_HOLD_MIN:
        decision = "MISSED_REBOOK"
        actions = (["WHEELCHAIR_AT_DOOR"] if "WCHR" in needs else []) + (
            ["ESCORT_TO_TRANSFER_DESK"] if needs else [])
    elif slack < HOLD_TRIGGER_SLACK_MIN:
        actions.append("GATE_HOLD_UP_TO_10_MIN")
        decision = "ASSIST_AND_HOLD_REQUESTED"
    elif actions:
        decision = "ASSIST_REQUESTED"
    else:
        decision = "SELF_GUIDED"

    if slack >= 10:
        verdict = "COMFORTABLE"
    elif slack >= 0:
        verdict = "TIGHT"
    else:
        verdict = "AT_RISK"
    return {"decision": decision, "verdict": verdict, "actions": actions,
            "self": self_calc, "slack_self": slack_self, "plan": eff_calc, "slack": slack,
            "minutes_left": minutes_left}


# ---------------------------------------------------------------- tool 3 (re-export)
from approval import request_mobility_dispatch_async  # noqa: E402,F401
