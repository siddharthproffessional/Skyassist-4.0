"""Browser end-to-end S1 demo (Playwright): passenger + coordinator in separate browser sessions.
Needs the app running (streamlit run app.py) on a fresh database.
Usage: python tests/e2e_browser_demo.py OUTDIR approve|decline"""
import sys

from playwright.sync_api import sync_playwright

out, mode = sys.argv[1], sys.argv[2]
BASE = "http://localhost:8501"
errors = []


def shot(page, name, full=True):
    page.wait_for_timeout(1200)
    page.screenshot(path=f"{out}/{name}.png", full_page=full)


def login(page, path, user, pw):
    page.goto(f"{BASE}/{path}", wait_until="networkidle")
    page.wait_for_selector("text=Sign in", timeout=30000)
    page.get_by_label("Booking reference" if path == "passenger" else "Coordinator username").fill(user)
    page.get_by_role("textbox", name="Password").fill(pw)
    page.get_by_role("button", name="Sign in").click()


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pax = b.new_context(viewport={"width": 1280, "height": 1900}).new_page()
    pax.on("pageerror", lambda e: errors.append(str(e)))
    login(pax, "passenger", "PNR1A2", "demo123")
    pax.wait_for_selector("text=Your next gate", timeout=30000)
    shot(pax, f"{mode}_01_passenger_home")
    pax.get_by_role("button", name="▶  Start navigation").click()
    pax.wait_for_selector("text=next instruction", timeout=20000)
    pax.get_by_role("button", name="✓  Mark step completed").click()
    pax.wait_for_timeout(1500)
    pax.get_by_role("button", name="✓  Mark step completed").click()
    pax.wait_for_timeout(1500)
    pax.locator("text=next instruction").first.scroll_into_view_if_needed()
    pax.wait_for_timeout(800)
    pax.screenshot(path=f"{out}/{mode}_02_passenger_navigation.png", clip={"x": 0, "y": 0, "width": 1280, "height": 1900})

    co = b.new_context(viewport={"width": 1600, "height": 2300}).new_page()
    co.on("pageerror", lambda e: errors.append(str(e)))
    login(co, "coordinator", "sarah", "coord123")
    co.wait_for_selector("text=Request queue", timeout=30000)
    co.get_by_role("button", name="Open REQ-").first.click()
    co.wait_for_selector("text=Deterministic calculation", timeout=20000)
    shot(co, f"{mode}_03_coordinator_pending")
    co.get_by_label("Operational note (shown to the passenger)").fill(
        "Cart #2 with Ravi meeting you at C12" if mode == "approve" else "No cart free in Concourse C")
    co.get_by_text("I have reviewed the passenger").click()
    if mode == "approve":
        co.get_by_role("button", name="✅ APPROVE REQUEST").click()
    else:
        co.get_by_role("button", name="❌ DECLINE REQUEST").click()
    co.wait_for_timeout(2500)
    shot(co, f"{mode}_04_coordinator_after")

    pax.wait_for_timeout(5500)
    pax.evaluate("window.scrollTo(0,0)")
    shot(pax, f"{mode}_05_passenger_updated")
    if mode == "approve":
        pax.get_by_role("tab", name="🛟  Assistance").click()
        pax.wait_for_timeout(2000)
        shot(pax, f"{mode}_06_passenger_assistance_tab")
    mob = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
    login(mob, "passenger", "PNR1A2", "demo123")
    mob.wait_for_selector("text=Your next gate", timeout=30000)
    shot(mob, f"{mode}_07_passenger_mobile", full=False)
    print("page errors:", errors)
    b.close()
