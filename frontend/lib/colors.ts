import type { GateStatus } from "./types";

export const C = {
  cyan: "#3ec5ff",
  green: "#34d399",
  amber: "#f5b544",
  red: "#f25f5c",
  violet: "#a78bfa",
  white: "#e9eef6",
  slate: "#5f6e84",
};

export const GATE_COLOR: Record<GateStatus, string> = {
  AVAILABLE: "#2a3a52",
  OCCUPIED: C.cyan,
  BOARDING: C.green,
  DEPARTING: C.green,
  BLOCKED: C.red,
  UNDER_REVIEW: C.amber,
  PENDING_APPROVAL: C.amber,
};

export const GATE_LABEL: Record<GateStatus, string> = {
  AVAILABLE: "Available",
  OCCUPIED: "Occupied",
  BOARDING: "Boarding",
  DEPARTING: "Departing",
  BLOCKED: "Blocked",
  UNDER_REVIEW: "Under review",
  PENDING_APPROVAL: "Pending approval",
};

export const HEALTH_COLOR = { normal: C.cyan, warning: C.amber, critical: C.red } as const;

export function statusTone(s?: string | null): "green" | "amber" | "red" | "cyan" | "violet" | "slate" {
  if (!s) return "slate";
  const u = s.toUpperCase();
  if (u === "AVAILABLE" || u === "IDLE" || u === "NOT CONFIGURED" || u === "NOT_CONFIGURED") return "slate";
  if (u === "OCCUPIED") return "cyan";
  if (/(REFUSED|BLOCKED|INVALID|ILLEGAL|FAIL|ROLLED|STALE|REJECT|CANCEL|CRITICAL|ESCALAT|EXPIRED|DECLIN)/.test(u)) return "red";
  if (/(AWAIT|PENDING|PAUSED|REVIEW|WARN|DELAY|HIGH|APPROVED$|TIGHT|DEGRADED|UNVERIFIED)/.test(u)) return "amber";
  if (/(OK|COMMIT|VALID|LEGAL|COMPLETE|EXECUTED|PASSED|HEALTHY|SUCCESS|APPROVED_EXECUTED|CLEARED|COMFORT|DECIDED)/.test(u)) return "green";
  if (/(RUNNING|ANALYS|INVESTIG|\bAI\b|AGENT)/.test(u)) return "violet";
  return "cyan";
}

export const TONE_HEX = { green: C.green, amber: C.amber, red: C.red, cyan: C.cyan, violet: C.violet, slate: C.slate };
