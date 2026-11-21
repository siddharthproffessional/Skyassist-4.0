"""SkyAssist 4.0 — measured latency of the digital-twin web API (server must be running on :8600).
Usage: python3 scripts/bench_v4.py [base_url] [n]"""
import json, statistics, sys, time, urllib.request, http.cookiejar
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8600"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
req = urllib.request.Request(BASE + "/web/auth/login", data=json.dumps({"username": "sarah", "password": "coord123", "portal": "COORDINATOR"}).encode(),
                             headers={"Content-Type": "application/json", "X-SkyAssist-Client": "web"})
op.open(req).read()
rows = []
for path in ["/web/twin/state", "/web/twin/layout", "/web/flights/SA-560", "/web/gates/B07", "/web/routes/connections",
             "/web/routes/baggage", "/web/agents", "/web/approvals", "/web/audit?limit=300", "/web/monitoring"]:
    ts = []
    for _ in range(N):
        t = time.perf_counter(); op.open(BASE + path).read(); ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    rows.append((path, statistics.median(ts), ts[int(len(ts) * 0.95) - 1], max(ts)))
print(f"| Endpoint | p50 ms | p95 ms | max ms |  (n={N} each, local)\n|---|---|---|---|")
for p, a, b, c in rows:
    print(f"| `{p}` | {a:.1f} | {b:.1f} | {c:.1f} |")
