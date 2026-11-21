"""SkyAssist 4.0 browser QA: drives every flow through the real UI and saves the screenshots in docs/v4/screenshots.
Usage: SKYASSIST_URL=http://localhost:8600 python3 scripts/qa_browser_v4.py [occ|recovery|pages|demo|pax|all]
Requires: pip install playwright && playwright install chromium. A reset of the synthetic dataset is done first unless NORESET=1."""
import os
import sys, time
from playwright.sync_api import sync_playwright
B = os.environ.get("SKYASSIST_URL", "http://localhost:8600"); import os
OUT = os.environ.get("SKYASSIST_SHOTS", "docs/v4/screenshots/")
ARGS = ["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"]
logs = []
def shot(pg, name, wait=0):
    if wait: pg.wait_for_timeout(wait)
    pg.screenshot(path=OUT + name); print("shot", name, flush=True)
def btn(pg, text, wait=4000, exact=False):
    loc = pg.get_by_role("button", name=text, exact=exact).first
    loc.wait_for(state="visible", timeout=30000)
    for _ in range(40):
        if loc.is_enabled(): break
        pg.wait_for_timeout(500)
    loc.dispatch_event("click"); pg.wait_for_timeout(wait)
which = sys.argv[1] if len(sys.argv) > 1 else "all"
with sync_playwright() as p:
    b = p.chromium.launch(args=ARGS)
    ctx = b.new_context(viewport={"width": 1680, "height": 945})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: logs.append(f"PAGEERROR {pg.url}: {e}"))
    pg.on("console", lambda m: logs.append(f"console.error {pg.url}: {m.text}") if m.type == "error" else None)
    pg.goto(B + "/login/"); pg.wait_for_timeout(1500)
    btn(pg, "Sign in to the command centre", 2500)
    pg.evaluate("sessionStorage.setItem('sa_intro','1')")
    import os
    if not os.environ.get("NORESET"): pg.evaluate("fetch('/web/scenarios/reset',{method:'POST',headers:{'X-SkyAssist-Client':'web','Content-Type':'application/json'},body:'{}'})")
    pg.wait_for_timeout(1000)
    if which in ("all", "occ"):
        pg.goto(B + "/occ/"); shot(pg, "01_main_3d_airport.png", 22000)
        pg.evaluate("window.__skyTwin.getState().select({kind:'flight', id:'SA-560'})"); shot(pg, "02_selected_flight.png", 9000)
        pg.evaluate("window.__skyTwin.getState().select({kind:'gate', id:'B07'})"); shot(pg, "03_selected_gate.png", 9000)
    if which in ("all", "recovery"):
        pg.goto(B + "/recovery/"); pg.wait_for_timeout(9000)
        btn(pg, "Trigger scenario", 12000); shot(pg, "07_u41_batch_failure.png")
        btn(pg, "Crew duty violation", 0); pg.wait_for_timeout(2500)
        btn(pg, "Trigger scenario", 12000); shot(pg, "08_u42_crew_legality.png")
        btn(pg, "Maintenance sign-off rejection", 0); pg.wait_for_timeout(2500)
        btn(pg, "Trigger scenario", 9000)
        btn(pg, "Submit valid replacement sign-off", 10000); shot(pg, "09_u43_maintenance_validation.png")
        btn(pg, "Baggage connection failure", 0); pg.wait_for_timeout(2500)
        btn(pg, "Trigger scenario", 12000); shot(pg, "10_u44_baggage_rerouting.png")
        btn(pg, "Gate conflict / stale approval", 0); pg.wait_for_timeout(2500)
        btn(pg, "Stage EK-812 → B07", 9000)
        btn(pg, "APPROVE", 6000, exact=True)
        btn(pg, "◆ Simulation event: another flight (SA-880) takes Gate B07", 8000)
        btn(pg, "EXECUTE APPROVED MOVE", 10000); shot(pg, "11_u45_stale_approval.png")
        btn(pg, "Corridor closure", 0); pg.wait_for_timeout(2500)
        btn(pg, "Close Skywalk B–C", 10000); shot(pg, "05_recovery_simulator_corridor.png")
        btn(pg, "Reopen Skywalk B–C", 4000)
    if which in ("all", "pages"):
        pg.goto(B + "/approvals/"); shot(pg, "06_approval_centre.png", 6000)
        pg.goto(B + "/agents/"); shot(pg, "04_agent_mission_control.png", 7000)
        pg.goto(B + "/monitoring/"); pg.wait_for_timeout(4000)
        btn(pg, "Run 12-alert burst (4 workers)", 12000); shot(pg, "13_monitoring.png")
        pg.goto(B + "/audit/"); shot(pg, "14_audit.png", 5000)
        pg.goto(B + "/occ/?mode=2d"); shot(pg, "15_occ_2d_fallback.png", 7000)
        pg.goto(B + "/occ/"); shot(pg, "16_occ_after_scenarios.png", 20000)
    if which in ("all", "demo"):
        pg.goto(B + "/demo/"); pg.wait_for_timeout(9000)
        btn(pg, "Start — restore the synthetic airport", 9000); shot(pg, "17_demo_1_identify.png")
        btn(pg, "Next — agents investigate (read-only)", 9000); shot(pg, "18_demo_2_investigate.png")
        btn(pg, "Next — recover", 14000); shot(pg, "19_demo_3_recover.png")
        btn(pg, "Next — human decision", 5000); shot(pg, "20_demo_4_decision.png")
        btn(pg, "APPROVE", 14000, exact=True); shot(pg, "21_demo_5_result.png", 4000)
    if which in ("all", "pax"):
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mp = m.new_page(); mp.on("pageerror", lambda e: logs.append(f"PAGEERROR pax: {e}"))
        mp.goto(B + "/passenger/login/"); mp.wait_for_timeout(1500)
        btn(mp, "Continue", 0); mp.wait_for_timeout(6000)
        mp.screenshot(path=OUT + "12_passenger_portal.png"); print("shot pax")
        mp.screenshot(path=OUT + "12b_passenger_portal_full.png", full_page=True)
    b.close()
print("\n".join(sorted(set(logs))[:40]))
