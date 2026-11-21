"""SkyAssist 4.0 — AGENT RUNTIME (permission-enforced tool calls + append-only execution record).

`Mission.call(agent_id, tool, ...)` is the ONLY way an agent acts:
  1 the Safety & Audit Supervisor checks the tool is on that agent's allowlist (else REFUSED + audit, no call)
  2 the tool runs the existing deterministic service (which applies its own RBAC, validation and transaction)
  3 the outcome is summarised from the service's own return value and appended to agent_steps

Nothing here invents activity: a step row exists only because a tool ran (or was refused), because a step of
the Round 3 alert journey was recorded by that journey, or because the mission is waiting for a recorded
human decision. agent_steps is append-only (DB triggers).
"""
import json
import re
import time

from db import query, query_one, tx, utcnow
from services.agents.registry import AGENTS, TOOLS
from services.auth_service import PermissionDenied
from services.ops.foundation import OpsError, audit, new_id, policy

MODULE = "AGENTS"


class ToolRefused(Exception):
    pass


def _epoch():
    try:
        return int(policy("demo.epoch", "1"))
    except Exception:
        return 1


def _short(obj, n=600):
    s = json.dumps(obj, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


# ------------------------------------------------------------------ result summaries (from the service's own output)
def summarize(tool, r):
    """Return (status, plain-language summary). Status vocabulary: OK, BLOCKED, AWAITING_APPROVAL, ESCALATED,
    FAILED_SAFELY, REJECTED."""
    if r is None:
        return "OK", "No result."
    if tool == "get_flight":
        return ("OK", f"{r['flight_no']}: {r['status']} at gate {r['gate']}" if r.get("found")
                else f"{r['flight_no']} not found in flight data — nothing invented")
    if tool == "list_affected_passengers":
        return "OK", f"{r['count']} passenger{'' if r['count'] == 1 else 's'} on {r['flight_no']}; {len(r['vulnerable'])} vulnerable (recorded needs)"
    if tool == "departure_status":
        return ("BLOCKED" if r.get("blocked") else "OK"), f"{r.get('flight_no', '')}: {r.get('label', '')}".strip()
    if tool == "crew_board":
        return "OK", f"{len(r)} crew assigned"
    if tool == "gate_detail":
        occ = ", ".join(o["flight_no"] for o in r["occupants"]) or "free"
        return "OK", f"Gate {r['gate']} v{r['version']}: {occ}"
    if tool == "rebooking_report":
        return "OK", f"{r['committed_passengers']}/{r['total']} committed"
    if tool == "baggage_feasibility":
        d = r.get("decision")
        if d == "SAME_FLIGHT":
            return "OK", f"Bags can travel with the passenger on {r['candidate_flight']}"
        if d == "SEPARATE_FLIGHT":
            return "OK", (f"Bag connection {r['connection_min']} min < {r['min_bag_transfer_min']} min minimum — "
                          f"bags go on {r['bag_flight']}")
        return "BLOCKED", r.get("reason") or f"Decision {d}"
    if tool == "validate_crew_legality":
        return ("OK" if r["verdict"] == "LEGAL" else "BLOCKED"), (
            f"{r['crew_id']}: {r['verdict']} (remaining {r['remaining_min']} vs required {r['required_min']} min)")
    if tool == "evaluate_flight_crew":
        v = ", ".join(f"{x['crew_id']} {x['verdict']}" for x in r["results"])
        props = [s["proposal_id"] for s in r["reserve_search"] if s.get("proposal_id")]
        st = "AWAITING_APPROVAL" if props else ("BLOCKED" if r["departure_blocked"] else "OK")
        return st, (f"{v}. Departure {'BLOCKED' if r['departure_blocked'] else 'clear'}. Duty counters "
                    f"{'unchanged' if r['duty_counters_unchanged'] else 'CHANGED'}."
                    + (f" Reserve proposal {props[0]} staged for controller." if props else ""))
    if tool == "submit_signoff_for_validation":
        if r["status"] == "VALID":
            return "OK", f"Sign-off {r['signoff_id']} VALIDATED — defect cleared; final release stays with authorised staff"
        return "BLOCKED", f"Sign-off {r['signoff_id']} INVALID — " + "; ".join(r.get("reasons") or [])[:300]
    if tool == "verify_audit_trail":
        return ("OK" if not r["missing"] else "FAILED_SAFELY"), (
            f"{r['events']} audit events across {r['checked']} entities" +
            (f"; missing for {', '.join(r['missing'])}" if r["missing"] else ""))
    if tool == "stage_gate_move":
        return "AWAITING_APPROVAL", (f"Staged {r['approval_id']}: {r['flight_no']} → {r['payload_dict']['gate']} "
                                     f"(versions {r['snapshot_dict']['versions']})")
    if tool == "revalidate_affected_approvals":
        return ("AWAITING_APPROVAL" if r else "OK"), (f"{len(r)} approval(s) marked STALE and re-staged" if r
                                                      else "No approval affected")
    if tool == "create_rebooking_job":
        return "OK", f"Job {r} created"
    if tool == "run_rebooking_job":
        esc = r.get("escalated") or []
        return ("ESCALATED" if esc else "OK"), (
            f"{r['committed_passengers']}/{r['total']} passengers committed; vulnerable first "
            f"({r['vulnerable']}); " + (f"batch {', '.join(esc)} ESCALATED to controller" if esc else "all batches committed"))
    if tool == "commit_rebooking_with_baggage":
        if r.get("status") == "COMMITTED":
            return "OK", f"Committed in one transaction {r.get('txn_id')}: seat + bag plan"
        return "FAILED_SAFELY", f"{r.get('status')}: {r.get('reason') or r.get('error') or 'nothing changed'}"
    if tool == "process_alert":
        st = {"PAUSED_FOR_APPROVAL": "AWAITING_APPROVAL", "BLOCKED": "BLOCKED", "REJECTED": "REJECTED",
              "REFUSED": "REJECTED"}.get(r.get("status"), "OK")
        return st, f"Run {r.get('run_id')}: {r.get('status')} — {r.get('summary') or ''}"[:400]
    if tool == "compose_passenger_update":
        return "OK", r["message"] or r.get("reason", "")
    if tool == "passenger_baggage_view":
        return "OK", ("No bags on booking" if not r else
                      f"{len(r['bags'])} bag(s); {'SEPARATE flight' if r['separate'] else 'with passenger'}")
    return "OK", _short(r, 200)


# ------------------------------------------------------------------ mission
class Mission:
    def __init__(self, principal, kind, title):
        self.principal = principal
        self.kind = kind
        self.mission_id = new_id("MSN")
        self.seq = 0
        self.refs = []           # entity ids touched (for the supervisor's audit check)
        with tx() as con:
            con.execute("INSERT INTO agent_missions(mission_id,kind,title,actor,status,epoch,created_at) "
                        "VALUES(?,?,?,?,'RUNNING',?,?)", (self.mission_id, kind, title, principal.display_name,
                                                          _epoch(), utcnow()))
            audit(con, principal.display_name, MODULE, "MISSION_STARTED", "mission", self.mission_id, new=kind,
                  reason=title)

    def _record(self, agent_id, tool, phase, status, args, summary, detail=None, ms=None, source="tool"):
        self.seq += 1
        with tx() as con:
            con.execute("INSERT INTO agent_steps(mission_id,seq,agent_id,tool,phase,status,args,result_summary,detail,"
                        "latency_ms,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.mission_id, self.seq, agent_id, tool, phase, status, _short(args or {}, 800), summary,
                         _short(detail, 3000) if detail is not None else None,
                         round(ms, 1) if ms is not None else None, source, utcnow()))

    def call(self, agent_id, tool, phase, **kwargs):
        agent = AGENTS.get(agent_id)
        if agent is None or tool not in agent["tools"] or tool not in TOOLS:
            reason = (f"{agent['name'] if agent else agent_id} is not authorised to use '{tool}'"
                      + ("" if tool in TOOLS else " (no such tool exists in the toolbox)"))
            self._record("safety_supervisor", tool, phase, "REFUSED", {"requested_by": agent_id, **kwargs},
                         f"REFUSED: {reason}", source="supervisor")
            with tx() as con:
                audit(con, self.principal.display_name, MODULE, "AGENT_TOOL_REFUSED", "mission", self.mission_id,
                      new={"agent": agent_id, "tool": tool}, reason=reason, result="REFUSED")
            raise ToolRefused(reason)
        fn = TOOLS[tool][0]
        t0 = time.perf_counter()
        try:
            r = fn(self.principal, **kwargs)
        except (OpsError, PermissionDenied) as e:
            ms = (time.perf_counter() - t0) * 1000
            code = getattr(e, "code", "PERMISSION_DENIED")
            self._record(agent_id, tool, phase, "REJECTED", kwargs, f"{code}: {e}", {"code": code}, ms)
            raise
        ms = (time.perf_counter() - t0) * 1000
        status, text = summarize(tool, r)
        self._record(agent_id, tool, phase, status, kwargs, text, r, ms)
        return r

    def note(self, agent_id, phase, status, text, detail=None, source="journey"):
        """Attach a step recorded elsewhere (Round 3 journey step, or a wait for a human decision)."""
        self._record(agent_id, None, phase, status, None, text, detail, source=source)

    def finish(self, status, summary, result=None):
        with tx() as con:
            con.execute("UPDATE agent_missions SET status=?, summary=?, result=?, finished_at=? WHERE mission_id=?",
                        (status, summary, _short(result, 20000) if result is not None else None, utcnow(),
                         self.mission_id))
            audit(con, self.principal.display_name, MODULE, "MISSION_FINISHED", "mission", self.mission_id,
                  new=status, reason=summary[:300] if summary else None, result=status)
        return self.mission_id


# ------------------------------------------------------------------ read models
def mission(mission_id):
    m = query_one("SELECT * FROM agent_missions WHERE mission_id=?", (mission_id,))
    if not m:
        return None
    m["steps"] = query("SELECT * FROM agent_steps WHERE mission_id=? ORDER BY seq", (mission_id,))
    for s in m["steps"]:
        s["agent_name"] = AGENTS.get(s["agent_id"], {}).get("name", s["agent_id"])
    _live_status(m)
    return m


def _live_status(m):
    """A mission recorded as AWAITING_APPROVAL shows DECIDED once no referenced human decision is still pending."""
    if m["status"] == "AWAITING_APPROVAL":
        steps = m.get("steps") or query("SELECT * FROM agent_steps WHERE mission_id=?", (m["mission_id"],))
        if not any(_still_waiting(x) for x in steps if x["status"] == "AWAITING_APPROVAL"):
            m["recorded_status"], m["status"] = m["status"], "DECIDED_BY_CONTROLLER"
    return m


def missions(limit=20):
    rows = query("SELECT * FROM agent_missions WHERE epoch=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                 (_epoch(), limit))
    for m in rows:
        m["step_count"] = query_one("SELECT COUNT(*) n FROM agent_steps WHERE mission_id=?", (m["mission_id"],))["n"]
        _live_status(m)
    return rows


LABELS = {"OK": "COMPLETED", "BLOCKED": "BLOCKED", "AWAITING_APPROVAL": "AWAITING APPROVAL",
          "ESCALATED": "ESCALATED TO CONTROLLER", "FAILED_SAFELY": "FAILED SAFELY", "REJECTED": "REJECTED",
          "REFUSED": "REFUSED CALL"}


_REF = re.compile(r"\b(APR|JAP|CRP)-[0-9A-F]{8}\b")


def _still_waiting(step):
    """An AWAITING_APPROVAL step stays 'awaiting' only while a referenced human decision is really pending."""
    text = (step["result_summary"] or "") + " " + (step["detail"] or "")
    for m in _REF.finditer(text):
        ref, kind = m.group(0), m.group(1)
        row = {"APR": ("approval_requests", "approval_id", ("PENDING", "APPROVED")),
               "JAP": ("journey_approvals", "approval_id", ("PENDING",)),
               "CRP": ("crew_assignment_proposals", "proposal_id", ("PENDING_APPROVAL",))}[kind]
        r = query_one(f"SELECT status FROM {row[0]} WHERE {row[1]}=?", (ref,))
        if r and r["status"] in row[2]:
            return True
    return False


def agent_statuses():
    """Each agent's status = its latest recorded step in the current synthetic dataset generation."""
    ep = _epoch()
    out = []
    for aid, a in AGENTS.items():
        s = query_one("SELECT s.* FROM agent_steps s JOIN agent_missions m USING(mission_id) WHERE s.agent_id=? AND "
                      "m.epoch=? ORDER BY s.step_id DESC LIMIT 1", (aid, ep))
        n = query_one("SELECT COUNT(*) n FROM agent_steps s JOIN agent_missions m USING(mission_id) WHERE "
                      "s.agent_id=? AND m.epoch=?", (aid, ep))["n"]
        if not s:
            status, label, text = "IDLE", "IDLE", "No activity recorded in this dataset generation"
        else:
            status = s["status"]
            if status == "AWAITING_APPROVAL" and not _still_waiting(s):
                status, label = "OK", "COMPLETED"
            else:
                label = LABELS.get(status, status)
            text = s["result_summary"]
        out.append({"agent_id": aid, **{k: a[k] for k in ("name", "short", "color", "responsibility", "tools",
                                                          "never")},
                    "status": status, "label": label, "last": text, "last_tool": s["tool"] if s else None,
                    "last_at": s["created_at"] if s else None, "mission_id": s["mission_id"] if s else None,
                    "steps": n})
    return out
