"use client";
import type { TwinState } from "@/lib/types";
import { statusTone, TONE_HEX } from "@/lib/colors";

function Item({ label, value, tone }: { label: string; value: React.ReactNode; tone?: keyof typeof TONE_HEX }) {
  return (
    <div className="flex items-center gap-2 px-3 border-r hairline last:border-r-0 h-full">
      <span className="label-xs whitespace-nowrap">{label}</span>
      <span className="mono text-[12px] font-semibold whitespace-nowrap" style={tone ? { color: TONE_HEX[tone] } : undefined}>{value}</span>
    </div>
  );
}

export default function StatusBar({ s, live }: { s?: TwinState; live: boolean }) {
  const k = s?.kpis;
  const prov = s?.health.providers ?? [];
  const ai = prov.some((p) => p.status === "HEALTHY") ? "AI healthy" : prov.every((p) => p.status === "NOT_CONFIGURED") ? "Rules-only" : "AI degraded";
  return (
    <footer className="h-8 shrink-0 flex items-stretch border-t hairline bg-[#070c16]/95 text-[12px] overflow-x-auto scroll-thin z-20 relative">
      <Item label="Active flights" value={k?.active_flights ?? "—"} />
      <Item label="Disrupted" value={k?.disrupted_flights ?? "—"} tone={k?.disrupted_flights ? "red" : undefined} />
      <Item label="Affected pax" value={k?.affected_passengers ?? "—"} tone={k?.affected_passengers ? "amber" : undefined} />
      <Item label="Approvals" value={k?.pending_approvals ?? "—"} tone={k?.pending_approvals ? "amber" : undefined} />
      <Item label="Recoveries" value={k?.successful_recoveries ?? "—"} tone="green" />
      <Item label="Failed txns" value={k?.failed_transactions ?? "—"} tone={k?.failed_transactions ? "red" : undefined} />
      <Item label="AI" value={ai} tone={ai === "AI healthy" ? "green" : ai === "Rules-only" ? "cyan" : "amber"} />
      <Item label="n8n" value={s?.health.n8n_mode?.replace(/_/g, " ").toLowerCase() ?? "—"} tone={statusTone(s?.health.n8n_mode) as any} />
      <Item label="Live" value={live ? "● stream" : "○ polling"} tone={live ? "green" : "amber"} />
      <div className="ml-auto px-3 flex items-center text-[10.5px] text-dim whitespace-nowrap">{s?.label}</div>
    </footer>
  );
}
