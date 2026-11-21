"use client";
import type { Agent } from "@/lib/types";
import { Chip } from "@/components/ui/primitives";
import { statusTone, TONE_HEX } from "@/lib/colors";
import { localTime } from "@/lib/format";

export const AGENT_GLYPH: Record<string, string> = {
  flight_intel: "◈", passenger_recovery: "⇄", crew_compliance: "✈", maintenance: "⚙", baggage: "▣",
  gate_resource: "⌖", communication: "✉", safety_supervisor: "⛨",
};

export default function AgentActivityPanel({ agents, dense = false, onPick }: { agents: Agent[]; dense?: boolean; onPick?: (a: Agent) => void }) {
  return (
    <ul className="flex flex-col">
      {agents.map((a) => {
        const tone = statusTone(a.status === "IDLE" ? null : a.status);
        const active = a.status !== "IDLE";
        return (
          <li key={a.agent_id}>
            <button onClick={() => onPick?.(a)} className="w-full text-left px-3.5 py-2 hover:bg-white/[0.03] border-t hairline first:border-t-0 group">
              <div className="flex items-center gap-2">
                <span className={`w-6 h-6 shrink-0 rounded-md grid place-items-center text-[12px] ${active ? "bg-violet/15 text-violet" : "bg-white/5 text-dim"}`} aria-hidden>
                  {AGENT_GLYPH[a.agent_id]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold tracking-[0.08em] truncate">{a.short}</span>
                    <Chip status={a.status === "IDLE" ? "IDLE" : a.status} label={a.label} tone={a.status === "IDLE" ? "slate" : tone} size="xs" />
                  </div>
                  {!dense && (
                    <div className="text-[11px] text-muted leading-snug line-clamp-2 mt-0.5" title={a.last}>
                      {a.last_tool && <span className="mono text-[10px] text-dim mr-1">{a.last_tool}()</span>}
                      {a.last}
                    </div>
                  )}
                </div>
              </div>
              {!dense && active && (
                <div className="h-[2px] mt-1.5 rounded-full overflow-hidden bg-white/5 ml-8">
                  <div className="h-full" style={{ width: `${Math.min(100, 12 + a.steps * 6)}%`, background: TONE_HEX[tone] }} />
                </div>
              )}
              {!dense && a.last_at && <div className="text-[9.5px] text-dim ml-8 mt-0.5 mono">{a.steps} recorded steps · last {localTime(a.last_at, true)}</div>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
