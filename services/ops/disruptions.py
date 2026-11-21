"""SkyAssist 4.0 — SYNTHETIC DISRUPTION EVENTS for the Recovery Simulator.

Labelled simulation events that change the synthetic flight data exactly the way an operational feed would:
versioned, audited and published through the outbox, inside one transaction. Controller-only.
"""
from db import tx, utcnow
from services.ops.foundation import OpsError, audit, bump, outbox, require_controller
from db import fmt, to_min

MODULE = "SIMULATOR"


def delay_flight(principal, flight_no, minutes):
    require_controller(principal)
    if not 5 <= int(minutes) <= 240:
        raise OpsError("BAD_DELAY", "Delay must be between 5 and 240 minutes.")
    with tx() as con:
        f = con.execute("SELECT * FROM flights WHERE flight_no=?", (flight_no,)).fetchone()
        if f is None:
            raise OpsError("UNKNOWN_FLIGHT", f"{flight_no} not found.")
        if f["status"] == "CANCELLED" or f["direction"] != "DEPARTURE":
            raise OpsError("NOT_DELAYABLE", f"{flight_no} is not an operating departure.")
        base = f["est"] or f["sched"]
        est = fmt(to_min(base) + int(minutes))
        close = fmt(to_min(f["boarding_close"]) + int(minutes)) if f["boarding_close"] else None
        con.execute("UPDATE flights SET status='DELAYED', est=?, boarding_close=? WHERE flight_no=?",
                    (est, close, flight_no))
        bump(con, f"FLIGHT:{flight_no}", event=f"DELAY +{minutes}")
        audit(con, principal.display_name, MODULE, "FLIGHT_DELAYED", "flight", flight_no,
              old={"status": f["status"], "est": base}, new={"status": "DELAYED", "est": est},
              reason=f"SYNTHETIC SIMULATION EVENT: +{minutes} min", result="COMMITTED")
        outbox(con, "flight.delayed", {"flight": flight_no, "est": est, "minutes": int(minutes)})
        for p in con.execute("SELECT booking_ref FROM passengers WHERE outbound=?", (flight_no,)):
            con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) "
                        "VALUES(?,?,'DELAY',?,?)", (p["booking_ref"], None,
                                                   f"{flight_no} is delayed: new departure {est}.", utcnow()))
    return {"flight": flight_no, "status": "DELAYED", "est": est, "boarding_close": close}
