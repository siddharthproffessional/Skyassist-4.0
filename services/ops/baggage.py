"""U-4.4 — PASSENGER & BAGGAGE CONSISTENCY.

A passenger may make a connection their bag cannot. No rebooking commits without a valid baggage plan, and the
seat, the booking update, the bag assignment(s), the delivery note, the rebooking record and the audit event
are written in ONE transaction. Any failure rolls all of it back.
"""
import json

import tools
from db import query, query_one, to_min, tx, utcnow
from services.ops.foundation import (OpsError, alert, audit, audit_now, idem_lookup, idem_store, new_id, outbox,
                                     policy, policy_row, require_ops)
from services.routing_engine import NoRouteError

MODULE = "BAGGAGE"
INJECTION_POINTS = ("after_seat", "after_booking", "after_bag", "after_note")


class InjectedFailure(Exception):
    """Deliberate failure used by tests and the simulator to prove rollback correctness."""


def _flight(no):
    f = tools.get_flight_and_gate_status(no)
    return f if f.get("found") else None


def _dep_time(f):
    return f.get("est") or f.get("sched")


def bag_capacity_left(flight_no, con=None):
    sql = "SELECT capacity - used AS left FROM baggage_capacity WHERE flight_no=?"
    r = (con.execute(sql, (flight_no,)).fetchone() if con else query_one(sql, (flight_no,)))
    return (r["left"] if r else 0)


def bags_for(booking_ref):
    return query("SELECT * FROM baggage_items WHERE booking_ref=? ORDER BY bag_tag", (booking_ref,))


def calculate_baggage_feasibility(booking_ref, candidate_flight):
    """Deterministic. Answers: (A) can the passenger make it, (B) can the bags, (C) alternative bag flight,
    (D) delivery to final destination, (E) can a delivery note be produced."""
    m = tools.get_passenger_manifest(booking_ref)
    if not m:
        raise OpsError("NO_BOOKING", f"Booking {booking_ref} not found.")
    inbound, cand = _flight(m["inbound"]), _flight(candidate_flight)
    if not inbound or not cand:
        raise OpsError("UNKNOWN_FLIGHT", "Inbound or candidate flight not found in flight data.")
    if cand["status"] == "CANCELLED" or cand["direction"] != "DEPARTURE":
        raise OpsError("FLIGHT_NOT_BOOKABLE", f"{candidate_flight} is not an operating departure.")
    rule = policy_row("baggage.min_transfer_min")
    if not rule or not int(rule["verified"]):
        return {"decision": "UNKNOWN", "reason": "Minimum baggage transfer time is not configured/verified — "
                "failing closed.", "passenger_feasible": None}
    min_bag = int(rule["value"])
    arrival = to_min(inbound.get("est") or inbound["sched"])
    connection = to_min(_dep_time(cand)) - arrival
    # (A) passenger: the existing deterministic transfer calculator (same engine as SkyAssist 2.0)
    try:
        t = tools.calculate_terminal_transfer_time(inbound["gate"], cand["gate"], m["needs"], "SELF")
        to_close = to_min(cand["boarding_close"]) - arrival if cand.get("boarding_close") else connection
        pax_ok = t["total_min"] <= to_close
        pax = {"feasible": pax_ok, "transfer_min": t["total_min"], "minutes_to_boarding_close": to_close}
    except NoRouteError as e:
        pax = {"feasible": False, "error": str(e)}
    bags = bags_for(booking_ref)
    n = len(bags)
    # (B) same-flight bags
    same_cap = bag_capacity_left(candidate_flight)
    same_ok = n == 0 or (connection >= min_bag and same_cap >= n)
    out = {"booking_ref": booking_ref, "candidate_flight": candidate_flight, "destination": cand["destination"],
           "passenger": pax, "passenger_feasible": pax["feasible"], "connection_min": connection,
           "min_bag_transfer_min": min_bag, "bag_rule_source": rule["source"], "bags": [b["bag_tag"] for b in bags],
           "same_flight": {"feasible": same_ok, "connection_min": connection, "capacity_left": same_cap,
                           "reason": None if same_ok else (
                               f"Bag connection {connection} min is below the {min_bag}-min minimum"
                               if connection < min_bag else "No baggage capacity left")}}
    if same_ok:
        out.update(decision="SAME_FLIGHT", bag_flight=candidate_flight, delivery_note=None)
        return out
    # (C)/(D) later flight to the same destination with capacity and a legal bag connection
    alts = []
    for f in query("SELECT flight_no FROM flights WHERE direction='DEPARTURE' AND destination=? AND status!='CANCELLED' "
                   "AND flight_no!=?", (cand["destination"], candidate_flight)):
        af = _flight(f["flight_no"])
        if not af:
            continue
        conn = to_min(_dep_time(af)) - arrival
        cap = bag_capacity_left(af["flight_no"])
        ok = conn >= min_bag and cap >= n and to_min(_dep_time(af)) > to_min(_dep_time(cand))
        alts.append({"flight_no": af["flight_no"], "departs": _dep_time(af), "connection_min": conn,
                     "capacity_left": cap, "viable": ok,
                     "reason": None if ok else ("capacity" if cap < n else "connection too short or not later")})
    out["alternatives"] = sorted(alts, key=lambda a: a["departs"])
    viable = [a for a in out["alternatives"] if a["viable"]]
    if not viable:
        out.update(decision="NO_VIABLE_PLAN", bag_flight=None,
                   reason="No later flight can carry the bags — the rebooking must not be committed.")
        return out
    best = viable[0]
    fo = query_one("SELECT dest_arrival FROM flight_ops WHERE flight_no=?", (best["flight_no"],))
    out.update(decision="SEPARATE_FLIGHT", bag_flight=best["flight_no"],
               delivery_note={"carrying_flight": best["flight_no"], "expected_arrival":
                              f"{cand['destination']} {fo['dest_arrival'] if fo else 'time to be confirmed'}",
                              "delivery_destination": f"{cand['destination']} baggage services, then courier to the "
                                                      f"delivery address on booking {booking_ref} (synthetic)"})
    return out


def _pick_seat(con, flight_no, exclude=()):
    for r in con.execute("SELECT seat_no FROM seat_inventory WHERE flight_no=? AND status='AVAILABLE' ORDER BY "
                         "CAST(substr(seat_no,1,length(seat_no)-1) AS INT), seat_no", (flight_no,)):
        if r["seat_no"] not in exclude:
            return r["seat_no"]
    return None


def reserve_seat_cas(con, flight_no, seat_no, booking_ref, txn_id):
    """Compare-and-set: succeeds only if the seat is still AVAILABLE inside this transaction."""
    cur = con.execute("UPDATE seat_inventory SET status='RESERVED', booking_ref=?, version=version+1 "
                      "WHERE flight_no=? AND seat_no=? AND status='AVAILABLE'", (booking_ref, flight_no, seat_no))
    if cur.rowcount != 1:
        raise OpsError("SEAT_CONFLICT", f"Seat {seat_no} on {flight_no} is no longer available.")
    con.execute("INSERT INTO seat_reservations VALUES(?,?,?,?,?,'ACTIVE',?)",
                (new_id("RES"), flight_no, seat_no, booking_ref, txn_id, utcnow()))


def apply_bag_plan(con, booking_ref, plan, txn_id, inject=None):
    """Assign every bag to the planned flight (capacity compare-and-set) and issue a delivery note when the bags
    travel separately. Must be called inside the passenger's rebooking transaction."""
    bags = [b["bag_tag"] for b in con.execute("SELECT bag_tag FROM baggage_items WHERE booking_ref=?", (booking_ref,))]
    if not bags:
        return None
    flight = plan["bag_flight"]
    cur = con.execute("UPDATE baggage_capacity SET used=used+?, version=version+1 WHERE flight_no=? AND used+?<=capacity",
                      (len(bags), flight, len(bags)))
    if cur.rowcount != 1:
        raise OpsError("BAG_CAPACITY", f"No baggage capacity left on {flight}.")
    kind = "WITH_PASSENGER" if plan["decision"] == "SAME_FLIGHT" else "SEPARATE"
    con.execute("UPDATE bag_flight_assignments SET status='SUPERSEDED' WHERE booking_ref=? AND status='ACTIVE'",
                (booking_ref,))
    for tag in bags:
        con.execute("INSERT INTO bag_flight_assignments VALUES(?,?,?,?,?,?,'ACTIVE',?)",
                    (new_id("BGA"), tag, booking_ref, flight, txn_id, kind, utcnow()))
        con.execute("UPDATE baggage_items SET status=? WHERE bag_tag=?",
                    ("ASSIGNED_" + kind, tag))
    if inject == "after_bag":
        raise InjectedFailure("Injected failure after baggage assignment")
    note_id = None
    if kind == "SEPARATE":
        dn = plan["delivery_note"]
        note_id = new_id("DN")
        con.execute("INSERT INTO baggage_delivery_notes VALUES(?,?,?,?,?,?,?,'ISSUED',?)",
                    (note_id, booking_ref, json.dumps(bags), dn["carrying_flight"], dn["expected_arrival"],
                     dn["delivery_destination"], txn_id, utcnow()))
    if inject == "after_note":
        raise InjectedFailure("Injected failure after delivery note")
    return {"bag_flight": flight, "kind": kind, "bags": bags, "delivery_note_id": note_id}


def commit_rebooking_with_baggage(principal, booking_ref, candidate_flight, idempotency_key=None, inject=None):
    """Atomic passenger + baggage rebooking. Returns a result dict; never claims success before COMMIT."""
    require_ops(principal)
    if inject and inject not in INJECTION_POINTS:
        raise ValueError(f"inject must be one of {INJECTION_POINTS}")
    actor = principal.display_name
    request = {"booking_ref": booking_ref, "candidate_flight": candidate_flight}
    if idempotency_key:
        prev = query_one("SELECT result, operation FROM idempotency_records WHERE idem_key=?", (idempotency_key,))
        if prev:
            if prev["operation"] != "REBOOK_WITH_BAGGAGE":
                raise OpsError("IDEMPOTENCY_KEY_REUSED", "Idempotency key already used for another operation.")
            r = json.loads(prev["result"])
            r["idempotent_replay"] = True
            return r
    plan = calculate_baggage_feasibility(booking_ref, candidate_flight)
    if plan["decision"] in ("NO_VIABLE_PLAN", "UNKNOWN") or not plan["passenger_feasible"]:
        reason = (plan.get("reason") if plan["decision"] in ("NO_VIABLE_PLAN", "UNKNOWN")
                  else "The passenger cannot make this flight in time.")
        audit_now(actor, MODULE, "REBOOKING_REFUSED", entity_type="booking", entity_id=booking_ref,
                  reason=reason, result="NOT_COMMITTED", new={"candidate": candidate_flight, "decision": plan["decision"]})
        with tx() as con:
            alert(con, MODULE, "HIGH", booking_ref, "Rebooking refused — no viable baggage plan"
                  if plan["decision"] == "NO_VIABLE_PLAN" else "Rebooking refused", reason)
        return {"status": "REFUSED", "committed": False, "reason": reason, "plan": plan}
    txn_id = new_id("TXN")
    m = tools.get_passenger_manifest(booking_ref)
    try:
        with tx() as con:
            replay = idem_lookup(con, idempotency_key, "REBOOK_WITH_BAGGAGE")
            if replay:
                replay["idempotent_replay"] = True
                return replay
            if con.execute("SELECT 1 FROM seat_reservations WHERE booking_ref=? AND flight_no=? AND status='ACTIVE'",
                           (booking_ref, candidate_flight)).fetchone():
                raise OpsError("DUPLICATE_BOOKING", f"{booking_ref} already holds a seat on {candidate_flight}.")
            seat = _pick_seat(con, candidate_flight)
            if not seat:
                raise OpsError("NO_SEAT", f"No seat available on {candidate_flight}.")
            reserve_seat_cas(con, candidate_flight, seat, booking_ref, txn_id)
            if inject == "after_seat":
                raise InjectedFailure("Injected failure after seat reservation")
            con.execute("UPDATE passengers SET outbound=? WHERE booking_ref=?", (candidate_flight, booking_ref))
            if inject == "after_booking":
                raise InjectedFailure("Injected failure after booking update")
            # re-validate mutable bag capacity inside the transaction (apply_bag_plan uses compare-and-set)
            bag = apply_bag_plan(con, booking_ref, plan, txn_id, inject)
            con.execute("INSERT INTO passenger_rebooking_history(booking_ref,from_flight,to_flight,seat_no,txn_id,"
                        "created_at) VALUES(?,?,?,?,?,?)", (booking_ref, m["outbound"], candidate_flight, seat, txn_id,
                                                            utcnow()))
            con.execute("INSERT INTO rebooking_transactions VALUES(?,?,?,?,'COMMITTED',?,?,?)",
                        (txn_id, None, None, "SINGLE_WITH_BAGGAGE", json.dumps({"seat": seat, "bag": bag}),
                         utcnow(), utcnow()))
            msg = f"You have been rebooked on {candidate_flight}, seat {seat}."
            if bag and bag["kind"] == "SEPARATE":
                msg += (f" Your bag(s) cannot make this connection and will travel separately on {bag['bag_flight']} "
                        f"(expected {plan['delivery_note']['expected_arrival']}); delivery note {bag['delivery_note_id']}."
                        f" Your bags will NOT arrive with you.")
            elif bag:
                msg += f" Your bag(s) are booked on the same flight."
            con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) "
                        "VALUES(?,?,?,?,?)", (booking_ref, None, "REBOOKED", msg, utcnow()))
            audit(con, actor, MODULE, "REBOOKING_COMMITTED", "booking", booking_ref,
                  old={"flight": m["outbound"]}, new={"flight": candidate_flight, "seat": seat, "bag": bag},
                  txn_id=txn_id, result="COMMITTED")
            result = {"status": "COMMITTED", "committed": True, "txn_id": txn_id, "seat": seat, "bag": bag,
                      "plan_decision": plan["decision"], "passenger_message": msg}
            idem_store(con, idempotency_key, "REBOOK_WITH_BAGGAGE", request, result)
            outbox(con, "rebooking.committed", {"booking_ref": booking_ref, "txn_id": txn_id, "flight": candidate_flight,
                                                "bag": bag})
        return result
    except (OpsError, InjectedFailure) as e:
        with tx() as con:
            con.execute("INSERT INTO rebooking_transactions VALUES(?,?,?,?,'ROLLED_BACK',?,?,?)",
                        (txn_id, None, None, "SINGLE_WITH_BAGGAGE", str(e), utcnow(), utcnow()))
            audit(con, actor, MODULE, "REBOOKING_ROLLED_BACK", "booking", booking_ref, txn_id=txn_id, reason=str(e),
                  result="ROLLED_BACK")
        return {"status": "ROLLED_BACK", "committed": False, "txn_id": txn_id, "reason": str(e),
                "code": getattr(e, "code", "INJECTED_FAILURE")}


def passenger_baggage_view(booking_ref):
    """Truthful passenger-facing baggage status (used by the passenger portal)."""
    bags = bags_for(booking_ref)
    if not bags:
        return None
    assigned = query("SELECT * FROM bag_flight_assignments WHERE booking_ref=? AND status='ACTIVE'", (booking_ref,))
    note = query_one("SELECT * FROM baggage_delivery_notes WHERE booking_ref=? AND status='ISSUED' ORDER BY created_at "
                     "DESC LIMIT 1", (booking_ref,))
    hist = query_one("SELECT * FROM passenger_rebooking_history WHERE booking_ref=? ORDER BY id DESC LIMIT 1",
                     (booking_ref,))
    return {"bags": bags, "assignments": assigned, "delivery_note": note, "rebooking": hist,
            "separate": any(a["kind"] == "SEPARATE" for a in assigned)}
