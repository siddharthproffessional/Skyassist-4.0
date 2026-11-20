"""Runs all 10 scenarios end-to-end in the terminal.
For each dispatch the agent pauses; we prove the event loop is still responsive, then an
auto-coordinator approves and we show the resumed message.   python run_scenarios.py"""
import time
import uuid

import build_db
from agent import Agent
from approval import ApprovalEngine
from db import connect

build_db.build()
engine = ApprovalEngine()
agent = Agent(engine, polish=True)

con = connect()
scenarios = [dict(r) for r in con.execute("SELECT * FROM scenarios ORDER BY CAST(SUBSTR(id,2) AS INT)")]
con.close()


def last_msgs(conv, n_before):
    con = connect()
    rows = con.execute("SELECT role,text FROM messages WHERE conv_id=? ORDER BY id", (conv,)).fetchall()
    con.close()
    return rows[n_before:]


passed = 0
for s in scenarios:
    conv = uuid.uuid4().hex[:8]
    print("\n" + "=" * 100 + f"\n{s['id']} · {s['title']}  [clock {s['now']}]\nPASSENGER: {s['message']}")
    res = agent.handle(conv, s["message"], s["booking_ref"], s["now"])
    for role, text in last_msgs(conv, 1):
        print(f"\nAGENT:\n{text}")
    if res.get("request_id"):
        print(f"\n⏸  PAUSED on {res['request_id']} — event-loop ping while waiting: {engine.ping_ms():.2f} ms")
        n = len(last_msgs(conv, 0))
        time.sleep(0.3)
        engine.resolve(res["request_id"], True, "AUTO-COORD (test)", "")
        for _ in range(300):
            new = last_msgs(conv, n)
            if new:
                print(f"▶  RESUMED:\n{new[-1][1]}")
                break
            time.sleep(0.1)
    ok = res["decision"] == s["expected"]
    passed += ok
    print(f"\nDECISION {res['decision']}  expected {s['expected']}  {'✅ PASS' if ok else '❌ FAIL'}")

print("\n" + "=" * 100 + f"\n{passed}/{len(scenarios)} scenarios passed")
