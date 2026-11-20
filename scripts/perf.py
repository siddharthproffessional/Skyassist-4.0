"""Measured timings for the five scenarios on this machine (synthetic dataset). Writes docs/PERFORMANCE.md.
Numbers are measured with time.perf_counter on whatever machine runs the script; they are not targets."""
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["SKYASSIST_DB"] = os.path.join(tempfile.mkdtemp(prefix="skyassist_perf_"), "p.sqlite")
os.environ.setdefault("SKYASSIST_PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("LLM_BACKEND", "rules")
sys.path.insert(0, str(ROOT))

import build_db  # noqa: E402
from services.auth_service import authenticate  # noqa: E402
from services.ops import baggage, maintenance, seed, simulator  # noqa: E402

RUNS = int(os.environ.get("PERF_RUNS", "5"))


def measure(label, fn):
    xs = []
    for _ in range(RUNS):
        build_db.build(reset=True)
        seed.seed_ops_demo()
        co = authenticate("sarah", "coord123", "COORDINATOR")
        t = time.perf_counter()
        fn(co)
        xs.append((time.perf_counter() - t) * 1000)
    return label, statistics.median(xs), min(xs), max(xs)


rows = [
    measure("U-4.1 full job: 40 pax, 5 transactions, batch-3 conflict + 2 retries + escalation", lambda c: simulator.run(c, "U-4.1")),
    measure("U-4.1 full job, no injected conflict", lambda c: simulator.run_u41(c, persistent_conflict=False)),
    measure("U-4.2 crew evaluation + reserve search (4 candidates)", lambda c: simulator.run(c, "U-4.2")),
    measure("U-4.3 invalid + valid sign-off validation", lambda c: simulator.run(c, "U-4.3")),
    measure("U-4.4 feasibility only", lambda c: baggage.calculate_baggage_feasibility("PNRBAG", "SA-592")),
    measure("U-4.4 atomic commit (seat + 2 bags + note)", lambda c: baggage.commit_rebooking_with_baggage(c, "PNRBAG", "SA-592", "p")),
    measure("U-4.5 stage, approve, conflicting change, stale refusal + restage", lambda c: simulator.run(c, "U-4.5")),
    measure("Single sign-off validation", lambda c: maintenance.submit_signoff(
        c, "E-501", "DEF-HYD-1", "A6-SKB", "HYDRAULIC", "OK", "2026-11-20T09:15:00+00:00", "WO-7781")),
]
md = ["# SkyAssist 3.0 — measured performance", "",
      f"Measured by `python scripts/perf.py` — {RUNS} runs each on a fresh synthetic SQLite database; "
      f"Python {platform.python_version()}, {platform.system()} {platform.machine()}. "
      "Timings are wall-clock for the service call only (database rebuild excluded). They describe this run on this "
      "machine, not a guarantee.", "", "| Operation | median ms | min ms | max ms |", "|---|---:|---:|---:|"]
for label, med, lo, hi in rows:
    md.append(f"| {label} | {med:.1f} | {lo:.1f} | {hi:.1f} |")
    print(f"{med:8.1f} ms  {label}")
(ROOT / "docs" / "PERFORMANCE.md").write_text("\n".join(md) + "\n")
