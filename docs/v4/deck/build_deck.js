// SkyAssist 4.0 deck — same structured frame as the Round 3 TechX deck (theme, DARK + CONTENT layouts, footer).
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const THEME = {
  name: "SkyAssist TechX",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1A2233", lt1: "FFFFFF", dk2: "0B2E6B", lt2: "EEF3FB",
    accent1: "1F5FBF", accent2: "19B5E6", accent3: "F2A93B", accent4: "2EAD6B",
    accent5: "7A869A", accent6: "CADCFC", hlink: "1F5FBF", folHlink: "7A869A",
  },
};
const IMG = __dirname + "/img/";
const FOOT = "TechX Dubai'26 · AI Agent Arena · SkyAssist 4.0";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "SkyAssist 4.0 — Airport Digital Twin";
pres.author = "Team SkyAssist";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

// pptxgenjs defines placeholders through `objects` with { placeholder: {...} }
pres.defineSlideMaster({
  title: "DARK_TITLE",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.35, w: 8.8, h: 1.3, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.8, w: 8.8, h: 1.2, fontSize: 18, color: C.accent6, valign: "top", align: "left" }, text: "" } },
    { text: { text: FOOT, options: { x: 0.6, y: 5.05, w: 6.0, h: 0.3, fontSize: 10, color: C.accent6 } } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.32, w: 6.9, h: 0.75, fontSize: 30, bold: true, color: C.text2, valign: "middle", align: "left" }, text: "" } },
    { text: { text: FOOT, options: { x: 0.5, y: 5.12, w: 6.0, h: 0.25, fontSize: 10, color: C.accent5 } } },
  ],
  slideNumber: { x: 9.0, y: 5.12, w: 0.5, h: 0.25, fontSize: 10, color: "7A869A", align: "right" },
});

// ------------------------------------------------------------------ helpers (template card language)
function tag(s, text) {
  s.addText(text, { x: 7.55, y: 0.45, w: 1.95, h: 0.48, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.24,
    fill: { color: C.accent1 }, color: C.background1, fontSize: 12, bold: true, align: "center", valign: "middle",
    isTextBox: true, objectName: "Section tag" });
}
function card(s, x, y, w, h, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: C.background2 },
    line: { color: C.accent6, width: 1 }, objectName: "Card: " + name });
}
function num(s, x, y, n, color) {
  s.addText(String(n), { x, y, w: 0.42, h: 0.42, shape: pres.shapes.OVAL, fill: { color: color || C.accent1 },
    color: C.background1, fontSize: 14, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function head(s, x, y, w, text, size) {
  s.addText(text, { x, y, w, h: 0.42, fontSize: size || 15, bold: true, color: C.text2, valign: "middle", margin: 0, isTextBox: true });
}
function body(s, x, y, w, h, text, size) {
  s.addText(text, { x, y, w, h, fontSize: size || 12, color: C.text1, valign: "top", margin: 0, isTextBox: true,
    paraSpaceAfter: 3 });
}
function numberedCard(s, x, y, w, h, n, title, text, opts = {}) {
  card(s, x, y, w, h, title);
  const t = h < 1.3 ? 0.12 : 0.18, b = h < 1.3 ? 0.58 : 0.72;
  num(s, x + 0.18, y + t, n, opts.color);
  head(s, x + 0.72, y + t, w - 0.9, title, opts.headSize);
  body(s, x + (h < 1.3 ? 0.72 : 0.2), y + b, w - (h < 1.3 ? 0.9 : 0.4), h - b - 0.08, text, opts.size);
}
function img(s, file, x, y, w, h, alt) {
  s.addImage({ path: IMG + file, x, y, w, h, altText: alt, objectName: alt.slice(0, 60),
    shadow: { type: "outer", color: "1A2233", opacity: 0.25, blur: 6, offset: 2, angle: 90 } });
}
function caption(s, x, y, w, text) {
  s.addText(text, { x, y, w, h: 0.25, fontSize: 10, italic: true, color: C.accent5, margin: 0, isTextBox: true });
}
function content(section, title, tagText) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  if (tagText) tag(s, tagText);
  return s;
}

// ================================================================== 1 · title
pres.addSection({ title: "Opening" });
let s = pres.addSlide({ masterName: "DARK_TITLE", sectionTitle: "Opening" });
s.addText("SkyAssist 4.0: the airport becomes the interface", { placeholder: "title" });
s.addText("3D airport digital twin + agentic operations command centre\nTeam SkyAssist  ·  University Track  ·  Domain 4: Aviation & Airport Operations",
  { placeholder: "body" });
s.addText("Live: skyassist-4.vercel.app   ·   Code: github.com/siddharthproffessional/Skyassist-4.0", {
  x: 0.6, y: 4.2, w: 8.8, h: 0.35, fontSize: 13, color: C.accent2, margin: 0, isTextBox: true });
s.addNotes("Open (10 s): SkyAssist 4.0 turns the airport itself into the operations interface. Everything you will see " +
  "is driven by our real backend: Python decides, the database is the truth, agents prepare, a human approves.");

// ================================================================== 2 · what changed
pres.addSection({ title: "Story" });
s = content("Story", "What changed since Round 3", "What's new");
card(s, 0.5, 1.3, 9.0, 1.0, "Our user and their problem");
head(s, 0.7, 1.42, 8.6, "Our user and their problem");
body(s, 0.7, 1.86, 8.6, 0.4, "OCC controllers juggle flights, gates, crew, bags and passengers across separate tables, and must connect the consequences in their heads.", 12);
numberedCard(s, 0.5, 2.5, 2.8, 1.95, 1, "After Round 3",
  "Five safe OCC workflows, a resilient AI chain and full audit, but shown as Streamlit tables and tabs.");
s.addShape(pres.shapes.RIGHT_ARROW, { x: 3.34, y: 3.3, w: 0.22, h: 0.35, fill: { color: C.accent6 }, line: { color: C.accent6 } });
numberedCard(s, 3.6, 2.5, 2.8, 1.95, 2, "New in 4.0",
  "A 3D digital twin of the 62-gate terminal; eight specialist agents with locked toolboxes; an Approval Centre; a guided demo.");
s.addShape(pres.shapes.RIGHT_ARROW, { x: 6.44, y: 3.3, w: 0.22, h: 0.35, fill: { color: C.accent6 }, line: { color: C.accent6 } });
numberedCard(s, 6.7, 2.5, 2.8, 1.95, 3, "Why it matters",
  "A disruption is understood by looking at the airport: red flight, highlighted gates, affected routes, then the fix.");
s.addNotes("20 s: Round 3 proved the safety and reliability. 4.0 makes it visible: the airport is the primary interface, " +
  "and every colour on it comes from the backend, not from the browser.");

// ================================================================== 3 · the twin
s = content("Story", "The airport is the interface", "Digital twin");
img(s, "16_occ_after_scenarios.png", 0.5, 1.3, 6.25, 3.52, "OCC command centre: 3D twin with disrupted flights, alerts and agent mission control");
const twinPts = [
  ["Every colour is backend state", "Gate status, aircraft tint and routes are read from the database, never computed in the browser."],
  ["Click any gate or aircraft", "The camera flies to it; the panel answers what happened, who is affected, what the AI is doing."],
  ["Honest by design", "Synthetic data, illustrative geometry; movement only in labelled simulation; 2D mode when 3D can't render."],
];
twinPts.forEach(([t, b], i) => {
  const y = 1.3 + i * 1.2;
  card(s, 6.95, y, 2.55, 1.08, t);
  head(s, 7.1, y + 0.08, 2.3, t, 12.5);
  body(s, 7.1, y + 0.46, 2.3, 0.6, b, 10.5);
});
s.addNotes("Point at the red aircraft and the left panel. Click SA-560: the camera flies to it, 40 bookings, 6 vulnerable. " +
  "Say: nothing on this screen is invented; the browser only renders verified state.");

// ================================================================== 4 · demo flow
s = content("Story", "One disruption, five steps", "Live demo");
const steps = [["Identify", "Two cancellations; heatmap shows who is affected"], ["Investigate", "Agents call read-only tools; nothing changes"],
  ["Recover", "Safe rebooking commits; risky case pauses"], ["Decide", "Controller approves the exact snapshot"], ["Result", "Twin updates; audit trail shows every step"]];
steps.forEach(([t, b], i) => {
  const x = 0.5 + i * 1.84;
  card(s, x, 1.3, 1.66, 1.3, t);
  num(s, x + 0.15, 1.42, i + 1);
  head(s, x + 0.62, 1.42, 1.0, t, 13);
  body(s, x + 0.15, 1.92, 1.4, 0.65, b, 10.5);
  if (i < 4) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 1.68, y: 1.82, w: 0.14, h: 0.3, fill: { color: C.accent6 }, line: { color: C.accent6 } });
});
img(s, "20_demo_4_decision.png", 0.5, 2.78, 4.35, 2.2, "Demo step 4: approval card for the Rahman family rebooking with separate bags");
img(s, "21_demo_5_result.png", 5.15, 2.78, 4.35, 2.2, "Demo step 5: twin shows the amber baggage line to SA-594 and the audit trail");
s.addNotes("Run /demo live (about 2 minutes). Identify, investigate (read-only), recover: SA-560 commits automatically, " +
  "SA-591 pauses because bags cannot make a 35-min connection vs a 45-min minimum. Click APPROVE. Show the amber bag line and the audit.");

// ================================================================== 5 · agents
pres.addSection({ title: "Agents and safety" });
s = content("Agents and safety", "Eight agents, locked toolboxes", "Agentic AI");
const agents = [
  ["Flight intelligence", "Alert intake, affected flights and passengers"],
  ["Passenger recovery", "Vulnerable first, batches of 10, escalation"],
  ["Crew compliance", "Duty validation, reserve proposals"],
  ["Maintenance", "Sign-off validation; never releases aircraft"],
  ["Baggage", "Bag feasibility, later-flight plan"],
  ["Gate & resource", "Versioned gate-move proposals"],
  ["Communication", "Wording from committed records only"],
  ["Safety supervisor", "Enforces allowlists, checks audit"],
];
agents.forEach(([t, b], i) => {
  const col = i % 4, row = Math.floor(i / 4);
  const x = 0.5 + col * 2.28, y = 1.3 + row * 1.2;
  card(s, x, y, 2.1, 1.05, t);
  head(s, x + 0.15, y + 0.08, 1.85, t, 12.5);
  body(s, x + 0.15, y + 0.48, 1.85, 0.55, b, 10.5);
});
card(s, 0.5, 3.8, 9.0, 1.05, "Boundary");
s.addText("✕", { x: 0.7, y: 3.98, w: 0.55, h: 0.55, shape: pres.shapes.OVAL, fill: { color: "D64545" }, color: C.background1,
  fontSize: 18, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true });
head(s, 1.45, 3.92, 7.9, "No agent has a tool to approve, execute, change duty limits or release an aircraft", 13.5);
body(s, 1.45, 4.36, 7.9, 0.45, "Runtime boundary test: 5 of 5 out-of-scope tool calls refused and written to the append-only audit. Every step is recorded with its tool, result and latency.", 11);
s.addNotes("Agents are real tool-using workers over our deterministic Python services, not animated labels. " +
  "Show /agents and run the permission boundary test live: 5/5 refused and audited.");

// ================================================================== 6 · five challenges table
s = content("Agents and safety", "All five OCC challenges, live in the twin", "U-4 workflows");
const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.accent1 }, fontSize: 12 } });
const cell = (t, o = {}) => ({ text: t, options: { fontSize: 11, color: C.text1, fill: { color: C.background1 }, ...o } });
const rows = [
  [hdr("Challenge"), hdr("What the twin and panels show"), hdr("Result on the backend")],
  [cell("U-4.1 Vulnerable first", { bold: true }), cell("Priority transaction, then batches of 10; batch 3 hits a seat conflict"), cell("Batch 3 failed. Previous successful batches were preserved.")],
  [cell("U-4.2 Crew legality", { bold: true }), cell("“Crew happy to extend duty” message; 20 min left vs 40 required"), cell("Departure blocked; counters unchanged; legal reserve proposed")],
  [cell("U-4.3 Maintenance sign-off", { bold: true }), cell("Unlicensed “OK” on a hydraulic defect, then a valid replacement"), cell("RED invalid, departure blocked → GREEN validated; release stays human")],
  [cell("U-4.4 Passenger vs bags", { bold: true }), cell("35-min passenger connection vs 45-min bag minimum"), cell("Seat + bag plan + delivery note in one transaction")],
  [cell("U-4.5 Stale approval", { bold: true }), cell("EK-812 → B07 approved, then SA-880 takes B07"), cell("Execution refused as STALE; fresh proposal needs a new decision")],
];
s.addTable(rows, { x: 0.5, y: 1.3, w: 9.0, colW: [2.2, 3.5, 3.3], border: { type: "solid", pt: 1, color: THEME.colors.accent6 },
  rowH: 0.52, valign: "middle", margin: 0.06, objectName: "U-4 results table" });
caption(s, 0.5, 4.62, 9.0, "Each run goes through the agents and the same Python services as Round 3; 25 new automated tests cover these flows.");
s.addNotes("Recovery Simulator: every control triggers a real backend operation, with BEFORE and AFTER twins and a diff of backend snapshots.");

// ================================================================== 7 · human approval + stale
s = content("Agents and safety", "Humans approve the exact state", "Safety");
img(s, "u45_panel.png", 0.5, 1.3, 2.47, 3.45, "U-4.5 stale approval: execution refused, approval marked STALE, fresh proposal staged");
const cases = [
  ["✓", "4AB37A", "Bound to a snapshot", "Approval is tied to the exact action, resource versions and snapshot hash the controller reviewed."],
  ["⏸", "F2A93B", "Expiry = no change", "Unanswered decisions expire and change nothing: 15 min for paused actions, 30 min for gate moves."],
  ["✕", "D64545", "Stale is refused", "If the state moved after approval, execution is refused and a fresh proposal is staged for a new decision."],
];
cases.forEach(([g, col, t, b], i) => {
  const y = 1.3 + i * 1.18;
  card(s, 3.25, y, 6.25, 1.06, t);
  s.addText(g, { x: 3.42, y: y + 0.25, w: 0.55, h: 0.55, shape: pres.shapes.OVAL, fill: { color: col }, color: C.background1,
    fontSize: 18, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true });
  head(s, 4.15, y + 0.1, 5.2, t, 14);
  body(s, 4.15, y + 0.52, 5.2, 0.5, b, 11.5);
});
s.addNotes("Show U-4.5 in /recovery: stage, APPROVE, simulate SA-880 taking B07, EXECUTE. Read the refusal: 'Another flight took Gate B07. " +
  "The previous approval is no longer valid.' Then approve the fresh proposal.");

// ================================================================== 8 · passenger
s = content("Agents and safety", "The passenger sees the truth", "Passenger");
img(s, "pax.png", 0.5, 1.25, 1.66, 3.6, "Passenger portal on a phone: rebooked to SA-592, bags travel separately on SA-594");
const pax = [
  ["Three states, never merged", "“Awaiting coordinator approval” is not “approved”, and “approved” is not “cart dispatched”."],
  ["Bags told plainly", "“Your bags will not arrive with you”, with the carrying flight and the delivery note."],
  ["Directions that fit", "Step-free routes from the same routing engine; a route is never invented when none exists."],
];
pax.forEach(([t, b], i) => numberedCard(s, 2.5, 1.25 + i * 1.22, 7.0, 1.1, i + 1, t, b, { size: 11.5, headSize: 14 }));
s.addNotes("Optional, on a phone: /passenger, booking PNRBAG / demo123. The portal is mobile-first and separate from the OCC.");

// ================================================================== 9 · proof
pres.addSection({ title: "Proof" });
s = content("Proof", "Nothing from Round 3 was lost", "Evidence");
const stats = [["239", "original tests, byte-identical"], ["265", "tests passing in 4.0"], ["10/10", "original passenger scenarios"], ["37 ms", "twin state p50 (p95 45 ms)"]];
stats.forEach(([v, l], i) => {
  const x = 0.5 + i * 2.3;
  card(s, x, 1.3, 2.1, 1.6, l);
  s.addText(v, { x: x + 0.1, y: 1.42, w: 1.9, h: 0.85, fontSize: 36, bold: true, color: C.accent1, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText(l, { x: x + 0.1, y: 2.3, w: 1.9, h: 0.5, fontSize: 11.5, color: C.text1, align: "center", valign: "top", margin: 0, isTextBox: true });
});
numberedCard(s, 0.5, 3.1, 4.4, 1.75, 1, "Additive only",
  "One two-line migration hook is the only change to existing code. Streamlit stays as the fallback; the n8n API is untouched and still can never approve.", { size: 11.5 });
numberedCard(s, 5.1, 3.1, 4.4, 1.75, 2, "Tested in a real browser",
  "Every flow clicked through on the production build: five U-4 flows, corridor closure, guided demo with a real approval, mobile portal. 0 page errors.", { size: 11.5 });
s.addNotes("Proof slide. Baseline captured before any change; test files hashed before and after. Latency measured on the demo container, n=40.");

// ================================================================== 10 · architecture
s = content("Proof", "Python decides, the twin renders", "Architecture");
const box = (x, y, w, h, t, sub, fill, txt) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: C.accent6, width: 1 }, objectName: "Arch: " + t });
  s.addText([{ text: t, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: sub, options: { fontSize: 10 } }],
    { x: x + 0.1, y, w: w - 0.2, h, color: txt, align: "center", valign: "middle", margin: 0, isTextBox: true });
};
const arrow = (x, y, w) => s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.28, fill: { color: C.accent5 }, line: { color: C.accent5 } });
box(0.5, 1.45, 1.95, 1.2, "3D twin", "Next.js · React Three Fiber", C.text2, C.background1);
arrow(2.5, 1.91, 0.35);
box(2.9, 1.45, 1.95, 1.2, "Web API", "signed session · CSRF guard", C.accent1, C.background1);
arrow(4.9, 1.91, 0.35);
box(5.3, 1.45, 1.95, 1.2, "8 agents", "allowlisted tools · recorded", "6B4FBB", C.background1);
arrow(7.3, 1.91, 0.35);
box(7.7, 1.45, 1.8, 1.2, "Python services", "validate · transact · audit", C.accent4, C.background1);
box(7.7, 3.05, 1.8, 1.0, "SQLite", "append-only audit", C.background2, C.text2);
s.addShape(pres.shapes.DOWN_ARROW, { x: 8.46, y: 2.7, w: 0.28, h: 0.3, fill: { color: C.accent5 }, line: { color: C.accent5 } });
box(2.9, 3.05, 1.95, 1.0, "Controller", "approve · decline · execute", C.accent3, C.text1);
box(0.5, 3.05, 1.95, 1.0, "n8n", "/v1 adapter, unchanged", C.background2, C.text2);
box(5.3, 3.05, 1.95, 1.0, "AI intake", "Gemini → Groq → rules", C.background2, C.text2);
caption(s, 0.5, 4.3, 9.0, "The browser never computes legality, seats, bag feasibility, clearance or approval validity. Only a human controller can approve or execute.");
s.addNotes("Architecture in one line: the twin renders verified state; agents act only through allowlisted tools over deterministic services; humans approve.");

// ================================================================== 11 · try it
s = content("Proof", "Try it now", "Deployment");
numberedCard(s, 0.5, 1.3, 4.4, 1.5, 1, "Live link", "skyassist-4.vercel.app · sign in sarah / coord123. Click Start in /demo first: serverless state resets after idle.", { size: 11.5 });
numberedCard(s, 5.1, 1.3, 4.4, 1.5, 2, "Run it locally", "One process, one port: uvicorn api.server:app --port 8600. Durable state; the frontend is prebuilt.", { size: 11.5 });
numberedCard(s, 0.5, 3.0, 4.4, 1.5, 3, "Code and docs", "github.com/siddharthproffessional/Skyassist-4.0 · C4 architecture, preservation register, test results, demo script.", { size: 11.5 });
numberedCard(s, 5.1, 3.0, 4.4, 1.5, 4, "Honest limits", "Synthetic data, illustrative geometry, demo sign-in. Omniverse/OpenUSD is a prepared interface, not connected.", { size: 11.5 });
s.addNotes("Close on what a judge can do in the next minute: open the link, run the demo, read the docs.");

// ================================================================== 12 · thank you
pres.addSection({ title: "Close" });
s = pres.addSlide({ masterName: "DARK_TITLE", sectionTitle: "Close" });
s.addText("Thank you", { placeholder: "title" });
s.addText("Live: https://skyassist-4.vercel.app\nCode: github.com/siddharthproffessional/Skyassist-4.0\nContact: SD1682@live.mdx.ac.uk",
  { placeholder: "body" });
s.addNotes("Thank you. Questions welcome; the live twin and repository are on screen.");

(async () => {
  const out = __dirname + "/SkyAssist_4.0_TechX.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("written", out);
})();
