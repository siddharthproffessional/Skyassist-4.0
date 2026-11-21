"""Round 3 latency benchmark: every sample alert + a 12-alert burst, on fresh synthetic databases.
Measures SkyAssist's own processing time (AI provider latency is logged separately in llm_calls when keys exist).
Writes docs/results/round3_latency.md."""
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["SKYASSIST_DB"] = os.path.join(tempfile.mkdtemp(prefix="r3bench_"), "b.sqlite")
os.environ.setdefault("SKYASSIST_PBKDF2_ITERATIONS", "1000")
os.environ["LLM_BACKEND"] = "rules"
sys.path.insert(0, str(ROOT))

import build_db  # noqa: E402
from services.auth_service import authenticate  # noqa: E402
from services.ops import burst, journey, seed  # noqa: E402

ROUNDS = int(os.getenv("ROUNDS", "10"))
per, walls = {}, []
for _ in range(ROUNDS):
    build_db.build(reset=True)
    seed.seed_ops_demo()
    co = authenticate("sarah", "coord123", "COORDINATOR")
    for name, text in journey.SAMPLES.items():
        r = journey.process_alert(co, text)
        per.setdefault(name, []).append(r["latency_ms"])
    build_db.build(reset=True)
    seed.seed_ops_demo()
    co = authenticate("sarah", "coord123", "COORDINATOR")
    b = burst.run_burst(co)
    walls.append(b["wall_ms"])


def pct(xs, q):
    xs = sorted(xs)
    return xs[max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))]


lines = ["# Round 3 — measured latency (SkyAssist processing only)", "",
         f"`python scripts/round3_bench.py` · {ROUNDS} runs per alert on fresh synthetic databases · Python "
         f"{platform.python_version()} on {platform.system()} {platform.machine()} · AI step in rules mode, so these "
         "numbers exclude provider latency (the live app logs provider latency per call in Monitoring).", "",
         "| Alert | p50 ms | p95 ms |", "|---|---:|---:|"]
for name, xs in per.items():
    lines.append(f"| {name} | {pct(xs, .5):.0f} | {pct(xs, .95):.0f} |")
lines += ["", f"Burst of 12 mixed alerts on 4 workers: wall time p50 {pct(walls, .5):.0f} ms, p95 {pct(walls, .95):.0f} ms."]
out = ROOT / "docs" / "results" / "round3_latency.md"
out.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
