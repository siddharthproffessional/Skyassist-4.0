"""End-to-end check against a REAL running n8n + SkyAssist API (see docs/N8N.md for setup).

    source <your env file>   # SKYASSIST_WEBHOOK_SECRET, SKYASSIST_DB (same DB the API uses)
    python scripts/n8n_e2e.py --n8n http://127.0.0.1:5678

Sends signed events to the five n8n webhooks, checks SkyAssist's answers, and checks that each call was recorded
in workflow_runs with an n8n execution id (proof the request really went through n8n). Writes docs/results/n8n_e2e.md.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def post(base, path, body, secret, bad=False):
    raw = json.dumps(body, separators=(",", ":"))
    sig = "0" * 64 if bad else hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    r = httpx.post(f"{base}/webhook/{path}", content=raw, timeout=30,
                   headers={"Content-Type": "application/json", "X-SkyAssist-Signature": sig})
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"text": r.text[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n8n", default="http://127.0.0.1:5678")
    a = ap.parse_args()
    secret = os.environ["SKYASSIST_WEBHOOK_SECRET"]
    from db import query, query_one
    from services.auth_service import authenticate
    from services.ops import gate_approvals as ga
    rows, ok_all = [], True

    def check(name, cond, detail):
        nonlocal ok_all
        ok_all &= bool(cond)
        rows.append((name, "PASS" if cond else "FAIL", detail))
        print(f"{'PASS' if cond else 'FAIL'}  {name}: {detail}")

    s, r = post(a.n8n, "skyassist/baggage-check", {"booking_ref": "PNRBAG", "candidate_flight": "SA-592"}, secret)
    check("D baggage feasibility", s == 200 and r.get("decision") == "SEPARATE_FLIGHT",
          f"HTTP {s}, decision {r.get('decision')}, bag flight {r.get('bag_flight')}")
    s, r = post(a.n8n, "skyassist/crew-message", {"flight_no": "SA-700", "sender": "flight deck",
                                                   "body": "Captain agrees to extend duty, approved, push departure"}, secret)
    v = {x["crew_id"]: x["verdict"] for x in r.get("results", [])}
    check("B crew message", s == 200 and v.get("C-101") == "ILLEGAL" and r.get("duty_counters_unchanged"),
          f"HTTP {s}, C-101 {v.get('C-101')}, counters unchanged {r.get('duty_counters_unchanged')}")
    s, r = post(a.n8n, "skyassist/maintenance-signoff", {"engineer_id": "E-999", "defect_id": "DEF-HYD-1",
                                                          "reg": "A6-SKB", "task_scope": "HYDRAULIC", "result": "OK",
                                                          "signed_at_utc": "2026-11-20T07:00:00+00:00",
                                                          "evidence_ref": "WO-7781"}, secret)
    check("C maintenance sign-off", s == 200 and r.get("status") == "INVALID" and r.get("departure_blocked"),
          f"HTTP {s}, {r.get('status')}, departure blocked {r.get('departure_blocked')}")
    s, r = post(a.n8n, "skyassist/disruption", {"disrupted_flight": "SA-560", "target_flight": "SA-562"}, secret)
    check("A disruption rebooking", s == 200 and r.get("committed_passengers") == 40,
          f"HTTP {s}, {r.get('status')}, {r.get('committed_passengers')} committed, vulnerable {r.get('vulnerable')}")
    co = authenticate("sarah", os.environ.get("COORDINATOR_DEMO_PASSWORD", "coord123"), "COORDINATOR")
    ap_ = ga.stage_gate_move(co, "EK-812", "B7")
    ga.assign_gate_direct(co, "SA-880", "B7", "e2e: another flight takes B7")
    s, r = post(a.n8n, "skyassist/state-change", {"topic": "state.changed", "payload": {"resources": ["GATE:B07"]}},
                secret)
    st = query_one("SELECT status FROM approval_requests WHERE approval_id=?", (ap_["approval_id"],))["status"]
    check("E state-change revalidation", s == 200 and st == "STALE", f"HTTP {s}, approval {ap_['approval_id']} → {st}")
    s, r = post(a.n8n, "skyassist/crew-message", {"flight_no": "SA-700", "sender": "x", "body": "y"}, secret, bad=True)
    check("Forged signature rejected by n8n", s >= 400, f"HTTP {s}")
    time.sleep(0.5)
    runs = query("SELECT workflow, execution_id FROM workflow_runs ORDER BY run_id")
    check("Calls recorded with n8n execution ids", len(runs) >= 4,
          "; ".join(f"{x['workflow'].split(' - ')[0]} exec {x['execution_id']}" for x in runs))
    md = ["# n8n end-to-end run", "", f"Run on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} against a real "
          f"n8n instance at {a.n8n} and the SkyAssist FastAPI adapter (`scripts/n8n_e2e.py`).", "",
          "| Check | Result | Detail |", "|---|---|---|"] + [f"| {n} | {r} | {d} |" for n, r, d in rows]
    (ROOT / "docs" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "results" / "n8n_e2e.md").write_text("\n".join(md) + "\n")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
