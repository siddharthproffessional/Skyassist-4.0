def test_reset_clears_ops_notices_keeps_v2(ops):
    from db import query_one, tx, utcnow
    from services.ops import seed
    with tx() as con:
        con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) VALUES(?,?,?,?,?)",
                    ("PNRBAG", None, "REBOOKED", "old run", utcnow()))
        con.execute("INSERT INTO notification_events(booking_ref,request_id,kind,message,created_at) VALUES(?,?,?,?,?)",
                    ("PNRBAG", "REQ-KEEP", "REQUESTED", "v2 request", utcnow()))
    seed.reset_ops_demo()
    assert query_one("SELECT COUNT(*) n FROM notification_events WHERE message='old run'")["n"] == 0
    assert query_one("SELECT COUNT(*) n FROM notification_events WHERE request_id='REQ-KEEP'")["n"] == 1
