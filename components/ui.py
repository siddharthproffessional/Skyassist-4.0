"""SkyAssist design system — shared HTML components and theme CSS for both portals.

Every value a component shows is passed in by the caller from backend services; components never compute
or invent operational data.
"""
import html

import streamlit as st

from db import local_time

TONE = {"good": ("#e7f6ec", "#15803d"), "warn": ("#fff4e0", "#b45309"), "bad": ("#fdecec", "#b91c1c"),
        "info": ("#e8f0fe", "#1d4ed8"), "neutral": ("#eef1f6", "#475569"), "pending": ("#fff4e0", "#b45309"),
        "dark": ("#0b2545", "#ffffff")}
RISK_TONE = {"COMFORTABLE": "good", "TIGHT": "warn", "AT_RISK": "bad"}
RISK_LABEL = {"COMFORTABLE": "COMFORTABLE", "TIGHT": "TIGHT", "AT_RISK": "AT RISK"}
STATE_TONE = {"PENDING": "pending", "APPROVED": "good", "DECLINED": "bad", "ESCALATED": "bad", "DISPATCHED": "info",
              "EN_ROUTE": "info", "COMPLETED": "neutral", "ASSIGNED": "info"}

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea, select { font-family: Inter, system-ui, sans-serif !important; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
[data-testid="stHeader"] { background: transparent; height: 0; }
.block-container { padding-top: 1.2rem; }
.sa-card { background:#fff; border:1px solid #e3e8f0; border-radius:16px; padding:16px 18px; margin-bottom:12px;
           box-shadow: 0 1px 2px rgba(11,37,69,.04); }
.sa-badge { display:inline-block; font-size:12px; font-weight:700; letter-spacing:.02em; padding:4px 10px;
            border-radius:999px; white-space:nowrap; }
.sa-muted { color:#5b6b82; font-size:13px; }
.sa-label { color:#5b6b82; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
.sa-big { font-size:30px; font-weight:800; color:#0b2545; line-height:1.1; }
.sa-legend { display:flex; flex-wrap:wrap; gap:12px; font-size:12px; color:#475569; margin:6px 2px 10px; }
.sa-legend i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
.sa-step { display:flex; gap:12px; padding:10px 0; border-bottom:1px dashed #e3e8f0; }
.sa-step .n { flex:none; width:28px; height:28px; border-radius:50%; background:#e8f0fe; color:#1d4ed8; font-weight:800;
              display:flex; align-items:center; justify-content:center; font-size:13px; }
.sa-step.done .n { background:#dbe8fb; color:#5b7fbf; } .sa-step.done .t { color:#6b7a93; text-decoration: line-through; }
.sa-step.cur .n { background:#f59e0b; color:#fff; } .sa-step.cur .t { font-weight:700; color:#0b2545; }
.sa-track { display:flex; gap:4px; margin:10px 0 4px; }
.sa-track div { flex:1; height:6px; border-radius:4px; background:#e3e8f0; }
.sa-track div.on { background:#1d4ed8; } .sa-track div.bad { background:#b91c1c; }
.sa-tl { border-left:2px solid #dbe3ef; margin-left:8px; padding-left:14px; }
.sa-tl .e { position:relative; padding:6px 0; font-size:13.5px; }
.sa-tl .e:before { content:''; position:absolute; left:-21px; top:11px; width:12px; height:12px; border-radius:50%;
                   background:#fff; border:3px solid #1d4ed8; }
.sa-tl .e .tm { color:#5b6b82; font-size:12px; margin-right:6px; font-variant-numeric: tabular-nums; }
.stButton > button, .stFormSubmitButton > button { border-radius:12px; min-height:44px; font-weight:600; }
[data-testid="stMetricValue"] { font-weight:800; }
"""

PASSENGER_CSS = BASE_CSS + """
.stApp { background:#f4f7fb; }
.block-container { max-width: 980px; }
.sa-hero { background: linear-gradient(135deg,#0b2545 0%,#13315c 60%,#1d4ed8 140%); color:#fff; border-radius:20px;
           padding:18px 20px; margin-bottom:14px; }
.sa-hero h1 { font-size:24px; margin:0 0 4px; color:#fff; font-weight:800; }
.sa-hero .sub { color:#c9d6ee; font-size:13px; }
.sa-gate { background:#0b2545; color:#fff; border-radius:18px; padding:18px 20px; }
.sa-gate .g { font-size:54px; font-weight:800; line-height:1; letter-spacing:-.02em; }
.sa-gate .was { display:inline-block; background:#fbbf24; color:#0b2545; font-weight:800; font-size:13px;
                border-radius:8px; padding:3px 8px; margin-left:8px; vertical-align:middle; }
.sa-risk { border-radius:18px; padding:16px 18px; margin-bottom:12px; }
.sa-risk .lv { font-size:26px; font-weight:800; letter-spacing:.02em; }
"""

COORDINATOR_CSS = BASE_CSS + """
.stApp { background:#eef2f7; }
.block-container { max-width: 1500px; padding-left:2rem; padding-right:2rem; }
section[data-testid="stSidebar"] { background:#0b1f3a; }
section[data-testid="stSidebar"] * { color:#dbe6f7 !important; }
section[data-testid="stSidebar"] .stButton > button { background:#13315c; border:1px solid #23477a; }
.sa-kpi { background:#fff; border:1px solid #dde4ee; border-radius:14px; padding:12px 14px; }
.sa-kpi .v { font-size:28px; font-weight:800; color:#0b2545; } .sa-kpi .l { font-size:12px; color:#5b6b82; font-weight:600; }
.sa-req { background:#fff; border:1px solid #dde4ee; border-left:6px solid #94a3b8; border-radius:12px; padding:10px 12px;
          margin-bottom:8px; font-size:13px; }
.sa-req.AT_RISK { border-left-color:#b91c1c; } .sa-req.TIGHT { border-left-color:#d97706; }
.sa-req.COMFORTABLE { border-left-color:#15803d; } .sa-req.resolved { opacity:.72; border-left-color:#94a3b8; }
.sa-req .id { font-weight:800; color:#0b2545; font-size:14px; }
.sa-grid { display:grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap:4px 14px; }
.sa-det td { padding:4px 8px; border-bottom:1px solid #edf1f6; font-size:13.5px; }
.sa-det td:first-child { color:#5b6b82; white-space:nowrap; }
.sa-calc { background:#f1f5fb; border:1px solid #d6e0ee; border-radius:12px; padding:10px 12px; }
.sa-ai { background:#f6f1ff; border:1px solid #e1d5fb; border-radius:12px; padding:10px 12px; }
"""


def inject(css):
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x)) if x is not None else "—"


def badge(text, tone="neutral"):
    bg, fg = TONE.get(tone, TONE["neutral"])
    return f'<span class="sa-badge" style="background:{bg};color:{fg}">{esc(text)}</span>'


def risk_badge(risk):
    return badge(RISK_LABEL.get(risk, risk), RISK_TONE.get(risk, "neutral"))


def card(inner, extra_style=""):
    return f'<div class="sa-card" style="{extra_style}">{inner}</div>'


def md(h):
    st.markdown(h, unsafe_allow_html=True)


def risk_banner(risk, headline, sub=""):
    bg, fg = TONE[RISK_TONE.get(risk, "neutral")]
    return (f'<div class="sa-risk" style="background:{bg};border:1px solid {fg}33">'
            f'<div class="sa-label" style="color:{fg}">Connection status</div>'
            f'<div class="lv" style="color:{fg}">{RISK_LABEL.get(risk, risk)}</div>'
            f'<div style="color:#1e293b;font-size:15px;margin-top:4px">{esc(headline)}</div>'
            f'{f"<div class=sa-muted style=margin-top:4px>{esc(sub)}</div>" if sub else ""}</div>')


def gate_card(gate, changed_from, flight_no, dest, close_time, status):
    was = f'<span class="was">CHANGED · was {esc(changed_from)}</span>' if changed_from else ""
    return (f'<div class="sa-gate"><div class="sa-label" style="color:#9fb6da">Your next gate</div>'
            f'<div><span class="g">{esc(gate)}</span>{was}</div>'
            f'<div style="margin-top:8px;color:#dbe6f7;font-size:15px">{esc(flight_no)} to {esc(dest)} · '
            f'boarding closes <b style="color:#fff">{esc(close_time)}</b> · {esc(status.replace("_", " "))}</div></div>')


def flight_card(kind, f, rows):
    tone = {"LANDED": "good", "ON_TIME": "good", "BOARDING": "warn", "GATE_CHANGED": "warn", "DELAYED": "warn",
            "CANCELLED": "bad"}.get(f.get("status"), "neutral")
    body = "".join(f'<tr><td>{esc(k)}</td><td style="text-align:right;font-weight:600">{v}</td></tr>' for k, v in rows)
    return card(f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<span class="sa-label">{esc(kind)}</span>{badge(f.get("status", "").replace("_", " "), tone)}</div>'
                f'<div style="font-size:22px;font-weight:800;color:#0b2545;margin:4px 0">{esc(f.get("flight_no"))}</div>'
                f'<table class="sa-det" style="width:100%;border-collapse:collapse">{body}</table>')


def tiles(items):
    cols = st.columns(len(items))
    for col, (label, value, sub) in zip(cols, items):
        col.markdown(card(f'<div class="sa-label">{esc(label)}</div><div class="sa-big">{esc(value)}</div>'
                          f'<div class="sa-muted">{esc(sub)}</div>', "padding:12px 14px"), unsafe_allow_html=True)


def tracker(view):
    labels = ["Requested", "Coordinator review", "Approved", "Dispatched", "Staff en route", "Completed"]
    idx = view.get("track_index", -1)
    bad = view.get("state") == "DECLINED"
    bars = "".join(f'<div class="{"bad" if bad and i == 1 else ("on" if i <= idx else "")}"></div>'
                   for i in range(len(labels)))
    names = "".join(f'<span style="flex:1;font-size:11px;color:{"#0b2545" if i <= idx else "#94a3b8"};'
                    f'font-weight:{700 if i == idx else 500}">{lbl}</span>' for i, lbl in enumerate(labels))
    return f'<div class="sa-track">{bars}</div><div style="display:flex;gap:4px">{names}</div>'


def assistance_card(view):
    tone = {"NO REQUEST REQUIRED": "neutral", "DECLINED": "bad", "ESCALATED": "bad"}.get(view["state"], view.get("tone", "pending"))
    tone = "good" if view["state"] in ("APPROVED", "DISPATCHED", "STAFF EN ROUTE", "COMPLETED") else tone
    if view["state"].startswith("PENDING"):
        tone = "pending"
    extra = ""
    if view.get("assigned_staff") or view.get("assigned_resource"):
        extra = (f'<div class="sa-muted" style="margin-top:6px">Assigned: '
                 f'{esc(", ".join(x for x in (view.get("assigned_staff"), view.get("assigned_resource")) if x))}</div>')
    req = view.get("request")
    meta = f'<div class="sa-muted" style="margin-top:6px">Request {esc(req["id"])}</div>' if req else ""
    return card(f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
                f'<span class="sa-label">Assistance status</span>{badge(view["state"], tone)}</div>'
                f'<div style="font-size:18px;font-weight:800;color:#0b2545;margin:6px 0 2px">{esc(view["headline"])}</div>'
                f'<div style="font-size:14.5px;color:#1e293b">{esc(view["detail"])}</div>{extra}{meta}'
                + (tracker(view) if req else ""))


def steps_list(steps, current=None):
    out = []
    for i, s in enumerate(steps):
        cls = "done" if current is not None and i < current else ("cur" if current == i else "")
        dist = f' <span class="sa-muted">· {int(s["distance_m"])} m</span>' if s.get("distance_m") else ""
        out.append(f'<div class="sa-step {cls}"><div class="n">{i + 1}</div><div class="t">{esc(s["text"])}{dist}</div></div>')
    return "".join(out)


def timeline(events):
    if not events:
        return '<div class="sa-muted">No events yet.</div>'
    rows = []
    for e in events:
        rows.append(f'<div class="e"><span class="tm">{esc(local_time(e["created_at"], "%H:%M:%S"))}</span>'
                    f'<b>{esc(e["event_type"].replace("_", " ").title())}</b> · <span class="sa-muted">{esc(e["actor"])}</span>'
                    f'{("<div class=sa-muted>" + esc(e["detail"]) + "</div>") if e.get("detail") and e["detail"] not in ("null", "{}") else ""}</div>')
    return f'<div class="sa-tl">{"".join(rows)}</div>'


def kpi(label, value):
    return f'<div class="sa-kpi"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div></div>'


def empty(text):
    return card(f'<div class="sa-muted" style="text-align:center;padding:18px 0">{esc(text)}</div>')
