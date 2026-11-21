"use client";
import type { TwinState } from "@/lib/types";
import { Chip, Empty } from "@/components/ui/primitives";
import { useTwin } from "@/lib/store";
import { localTime } from "@/lib/format";

export default function OperationalAlertPanel({ s }: { s: TwinState }) {
  const select = useTwin((x) => x.select);
  const disrupted = s.flights.filter((f) => f.health !== "normal");
  const order = { critical: 0, warning: 1, normal: 2 } as const;
  disrupted.sort((a, b) => order[a.health] - order[b.health]);
  const conflicts = s.gates.filter((g) => g.stale_approvals.length);
  return (
    <div className="flex flex-col">
      <div className="px-3.5 pb-1 label-xs">Flights needing attention · {disrupted.length}</div>
      {disrupted.length === 0 && <Empty>No disrupted flights in the current state.</Empty>}
      <ul>
        {disrupted.map((f) => (
          <li key={f.flight_no}>
            <button onClick={() => select({ kind: "flight", id: f.flight_no })}
              className="w-full text-left px-3.5 py-2 border-t hairline hover:bg-white/[0.03] flex items-start gap-2.5">
              <span className="mt-1 w-1.5 h-8 rounded-full shrink-0" style={{ background: f.health === "critical" ? "#f25f5c" : "#f5b544" }} aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="mono text-[12.5px] font-semibold">{f.flight_no}</span>
                  <Chip status={f.status === "CANCELLED" ? "CANCELLED" : f.holds.length ? "BLOCKED" : f.status}
                    label={f.status === "CANCELLED" ? "CANCELLED" : f.holds.length ? "BLOCKED" : f.reasons[0]?.toUpperCase() ?? f.status} size="xs" />
                </div>
                <div className="text-[11px] text-muted truncate">
                  {f.direction === "DEPARTURE" ? `→ ${f.destination}` : `← ${f.origin}`} · Gate {f.gate ?? "—"}
                  {f.previous_gate && f.status === "GATE_CHANGED" ? ` (was ${f.previous_gate})` : ""} · {f.passengers} pax
                </div>
                {f.holds.map((h, i) => <div key={i} className="text-[10.5px] text-red/90 truncate">{h.type}: {h.reason}</div>)}
              </div>
            </button>
          </li>
        ))}
      </ul>
      {conflicts.length > 0 && (
        <>
          <div className="px-3.5 pt-3 pb-1 label-xs">Gate conflicts</div>
          {conflicts.map((g) => (
            <button key={g.gate} onClick={() => select({ kind: "gate", id: g.gate })}
              className="w-full text-left px-3.5 py-2 border-t hairline hover:bg-white/[0.03] text-[11.5px]">
              <Chip status="STALE" label={`GATE ${g.gate}`} size="xs" />{" "}
              <span className="text-muted">Another flight took Gate {g.gate}. The previous approval is no longer valid.</span>
            </button>
          ))}
        </>
      )}
      <div className="px-3.5 pt-3 pb-1 label-xs">Open operational alerts · {s.alerts.length}</div>
      {s.alerts.length === 0 && <Empty>No open alerts.</Empty>}
      <ul>
        {s.alerts.slice(0, 14).map((a) => (
          <li key={a.alert_id} className="px-3.5 py-2 border-t hairline">
            <div className="flex items-center gap-2">
              <Chip status={a.severity === "CRITICAL" ? "CRITICAL" : "HIGH"} label={a.module} size="xs" />
              <span className="text-[10px] text-dim mono ml-auto">{localTime(a.created_at)}</span>
            </div>
            <div className="text-[11.5px] mt-1 leading-snug">{a.title}</div>
            {a.detail && <div className="text-[10.5px] text-muted leading-snug line-clamp-2">{a.detail}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
