"""THE LLM BRAIN — only two jobs:
  1. parse_message(): stressed free text  ->  structured JSON (flights, needs, claimed gate, language)
  2. polish_reply(): rewrite a code-generated draft in a calm tone / the passenger's language

Hallucination guards:
  * every flight code the LLM extracts must match a strict pattern; the rule parser is always unioned in
  * needs are a closed vocabulary and keyword-detected needs can never be dropped (priority floor)
  * polished replies are rejected if they contain ANY number, time, gate or flight code not in the draft,
    or claim confirmation while a request is still pending -> falls back to the deterministic draft
Backends (via services/ai/gateway.py): Gemini -> Groq -> (Ollama) -> rule-based fallback (offline, always works).
"""
import json
import os
import re
import time

try:
    import requests
except ImportError:  # rule-based mode still works
    requests = None

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
BACKEND = os.getenv("LLM_BACKEND", "auto")  # auto | ollama | gemini | groq | rules

NEEDS = ["WCHR", "UMNR", "ELDERLY", "STROLLER"]
FLIGHT_RE = re.compile(r"\b([A-Z]{2,3})[- ]?(\d{3,4})\b")
TOKEN_RE = re.compile(r"\b(?:[A-Z]{2,3}-\d{3,4}|[ABC]\d{1,2}|\d{1,2}:\d{2}|\d+)\b")

_status = {"checked": 0, "backend": None}


def _ollama_up():
    if requests is None:
        return False
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=1).ok
    except Exception:
        return False


def active_backend():
    from services.ai import gateway
    if BACKEND != "auto":
        return BACKEND
    chain = gateway.configured_chain()
    if chain:
        return " → ".join(chain + ["rules"])
    if time.time() - _status["checked"] < 30 and _status["backend"]:
        return _status["backend"]
    if _ollama_up():
        b = "ollama"
    elif os.getenv("GEMINI_API_KEY"):
        b = "gemini"
    elif os.getenv("GROQ_API_KEY"):
        b = "groq"
    else:
        b = "rules"
    _status.update(checked=time.time(), backend=b)
    return b


def _strip_think(t):
    return re.sub(r"<think>.*?</think>", "", t or "", flags=re.S).strip()


def _call(system, user, json_mode, purpose="passenger"):
    """All LLM traffic goes through the resilient gateway (fallback chain, timeouts, retries, logging).
    Returns (text_or_None, backend_label) exactly as before, so every caller keeps its deterministic fallback."""
    from services.ai import gateway
    text, label, _trace = gateway.complete(system, user, json_mode=json_mode, purpose=purpose)
    if text is None:
        return None, label
    return _strip_think(text), label


# ------------------------------------------------------------------ rule parser (always on)
def rule_parse(text):
    up = text.upper()
    flights = [f"{a}-{n}" for a, n in FLIGHT_RE.findall(up)]
    t = text.lower()
    needs = set()
    if re.search(r"wheel ?chair|व्हीलचेयर|can'?t walk|cannot walk", t):
        needs.add("WCHR")
    if re.search(r"unaccompanied|travell?ing alone|i'?m 1[0-7]\b|i am 1[0-7]\b|i'?m [5-9]\b|minor", t):
        needs.add("UMNR")
    if re.search(r"grand(mother|father|ma|pa)|elderly|walk slowly|\b[6-9]\d years old|dadi|nani|dada|nana", t):
        needs.add("ELDERLY")
    if re.search(r"stroller|pram|buggy|toddler|baby|infant|kids", t):
        needs.add("STROLLER")
    m = re.search(r"gate\s*(?:changed\s*to|is|number|no\.?|says\s*gate)?\s*([ABC])\s?-?(\d{1,2})\b", text, re.I) or \
        re.search(r"\bgate\s+([ABC])(\d{1,2})\b", text, re.I)
    claimed = f"{m.group(1).upper()}{int(m.group(2)):02d}" if m else None
    lang = "hi" if re.search(r"\b(hum|hai|hain|chahiye|ki|se|aaye|kya|kahan|mera|meri)\b", t) else "en"
    return {"flights": list(dict.fromkeys(flights)), "needs": sorted(needs), "claimed_gate": claimed,
            "language": lang, "urgency": "HIGH" if re.search(r"!|only|minutes|hurry|help", t) else "NORMAL",
            "intent": rule_intent(t)}


INTENTS = ["JOURNEY", "STATUS", "DESK", "LATE"]


def rule_intent(t):
    t = t.lower()
    if re.search(r"(has|is|was) my (assistance|request|wheelchair|cart|escort)|been approved|request status|"
                 r"approved\?|status of my|approve hua|confirm hua", t):
        return "STATUS"
    if re.search(r"(nearest|closest|where is( the)?) (assistance|help|transfer|information)? ?(desk|point|counter)|"
                 r"assistance (desk|point)|help desk|transfer desk", t):
        return "DESK"
    if re.search(r"running late|i am late|i'm late|we are late|we're late|late ho|miss(ing)? (my|our|the) (flight|connection)", t):
        return "LATE"
    return "JOURNEY"


PARSE_SYSTEM = (
    "You extract facts from an airport passenger's message. Reply ONLY with JSON: "
    '{"flights": ["XX-123"], "needs": [], "claimed_gate": null, "language": "en", "urgency": "HIGH|NORMAL", '
    '"intent": "JOURNEY|STATUS|DESK|LATE"}. '
    "intent: STATUS = asks whether assistance was approved; DESK = asks for the nearest help/transfer desk; "
    "LATE = says they are running late; otherwise JOURNEY. "
    "needs may only contain: WCHR (wheelchair), UMNR (child travelling alone), ELDERLY, STROLLER (young kids/pram). "
    "claimed_gate is the departure gate the passenger SAYS they have, like B14, else null. "
    "language is an ISO code of the language the passenger writes in (Hinglish = hi). Never invent flights."
)


def parse_message(text):
    rules = rule_parse(text)
    raw, backend = _call(PARSE_SYSTEM, text, json_mode=True)
    if raw is None:
        return rules, backend
    try:
        data = json.loads(raw)
    except Exception:
        return rules, f"{backend} (bad JSON → rules)"
    flights = [f"{a}-{n}" for f in data.get("flights", []) for a, n in FLIGHT_RE.findall(str(f).upper())]
    out = {
        "flights": list(dict.fromkeys(rules["flights"] + flights)),
        # priority floor: keyword-detected needs can never be dropped by the LLM
        "needs": sorted(set(rules["needs"]) | {n for n in data.get("needs", []) if n in NEEDS}),
        "claimed_gate": rules["claimed_gate"] or data.get("claimed_gate"),
        "language": data.get("language") or rules["language"],
        "urgency": data.get("urgency", rules["urgency"]),
        # deterministic intent wins; the LLM may only refine a plain JOURNEY message, within a closed set
        "intent": rules["intent"] if rules["intent"] != "JOURNEY" else (
            data.get("intent") if data.get("intent") in INTENTS else "JOURNEY"),
    }
    return out, backend


POLISH_SYSTEM = (
    "You rewrite an airport assistant message for a stressed family. Language: {lang}. "
    "Keep it calm, warm, short, numbered steps kept. COPY every number, time, gate and flight code EXACTLY "
    "as digits. Do NOT add any fact, time, gate, promise or flight status that is not in the draft. "
    "If the draft says help is requested/not confirmed, you must NOT say it is confirmed. Output only the message."
)


def guard(draft, candidate, pending):
    allowed = set(TOKEN_RE.findall(draft))
    used = set(TOKEN_RE.findall(candidate or ""))
    extra = used - allowed
    if extra:
        return False, f"rejected: new facts {sorted(extra)}"
    if pending and re.search(r"\bconfirmed\b", candidate, re.I) and not re.search(r"not (yet )?confirmed", candidate, re.I):
        return False, "rejected: claimed confirmation while pending"
    if len(candidate) < 0.4 * len(draft):
        return False, "rejected: dropped content"
    return True, "passed"


def polish_reply(draft, language="en", pending=False):
    raw, backend = _call(POLISH_SYSTEM.format(lang=language), draft, json_mode=False)
    if raw is None:
        return draft, backend, "skipped (no LLM)"
    ok, why = guard(draft, raw, pending)
    return (raw if ok else draft), backend, why


SUMMARY_SYSTEM = (
    "You are briefing an airport terminal coordinator. Summarise the facts below in 2-3 short sentences: who needs "
    "help, why, and how tight the connection is. COPY every number, time, gate and flight code EXACTLY. Do not add "
    "any fact or recommendation that is not in the facts. Output only the summary."
)


def summarize_situation(facts: str):
    """Optional AI explanation for coordinators. Guarded exactly like passenger replies; returns
    (text, source) where source says whether an LLM wrote it or the deterministic template was used."""
    raw, backend = _call(SUMMARY_SYSTEM, facts, json_mode=False)
    if raw is None:
        return facts, "template (no LLM available)"
    ok, why = guard(facts, raw, pending=True)
    return (raw, f"AI summary ({backend}, guard passed)") if ok else (facts, f"template (AI text {why})")
