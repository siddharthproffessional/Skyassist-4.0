"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import PageShell from "@/components/shell/PageShell";
import { Btn, Chip } from "@/components/ui/primitives";
import { get } from "@/lib/api";
import { localTime } from "@/lib/format";

const CATS: [RegExp, string][] = [
  [/ATTACK|INJECTION/, "Injection screening"], [/JOURNEY_|AI_/, "Alert journey / AI"], [/AGENT|MISSION/, "Specialist agents"],
  [/LEGALITY|SIGNOFF|VALIDAT|FEASIB/, "Python validation"], [/APPROVAL_(STAGED|RESTAGED)|PAUSED|PROPOSAL_STAGED/, "Approval requested"],
  [/EXPIRED/, "Approval expired"], [/GRANTED|REJECTED|DECID|APPROVED/, "Human decision"],
  [/ROLLED_BACK|ROLLBACK/, "Transaction rolled back"], [/COMMITTED|EXECUTED|BATCH_/, "Transaction / action"],
  [/NOTIF|REBOOK/, "Passenger impact"],
];
const cat = (e: any) => CATS.find(([r]) => r.test(e.event_type))?.[1] ?? e.module ?? "Event";

export default function AuditPage() {
  const [f, setF] = useState<Record<string, string>>({});
  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    const init: Record<string, string> = {};
    ["flight", "passenger", "agent", "module", "event_type", "result"].forEach((k) => { const v = u.get(k); if (v) init[k] = v; });
    if (Object.keys(init).length) setF(init);
  }, []);
  const qs = useMemo(() => new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString(), [f]);
  const q = useQuery({ queryKey: ["audit", qs], queryFn: () => get(`/web/audit?limit=400&${qs}`) });
  const [open, setOpen] = useState<number | null>(null);
  const set = (k: string) => (e: any) => setF((x) => ({ ...x, [k]: e.target.value }));
  const input = "bg-black/30 ring-1 ring-line-2 rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:ring-cyan";
  return (
    <PageShell title="Operational Audit"
      subtitle={<>Append-only record of every critical step — failures as well as successes. {q.data?.append_only}</>}
      actions={<a href={`/web/audit.csv?${qs}`}><Btn tone="primary">Export CSV</Btn></a>}>
      <div className="glass rounded-xl p-3 mb-4 flex flex-wrap gap-2 items-center">
        <input placeholder="Flight (e.g. SA-700)" className={input} value={f.flight ?? ""} onChange={set("flight")} />
        <input placeholder="Passenger (e.g. PNRBAG)" className={input} value={f.passenger ?? ""} onChange={set("passenger")} />
        <select className={input} onChange={set("agent")} defaultValue="">
          <option value="">Any agent</option>
          {["flight_intel", "passenger_recovery", "crew_compliance", "maintenance", "baggage", "gate_resource", "communication", "safety_supervisor"].map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select className={input} onChange={set("module")} defaultValue="">
          <option value="">Any workflow</option>
          {(q.data?.modules ?? []).map((m: string) => <option key={m}>{m}</option>)}
        </select>
        <input type="date" className={input} onChange={set("date")} />
        <input placeholder="Event type" className={input} onChange={set("event_type")} />
        <select className={input} onChange={set("result")} defaultValue="">
          <option value="">Any safety decision</option>
          {(q.data?.results ?? []).map((m: string) => <option key={m}>{m}</option>)}
        </select>
        <span className="ml-auto text-[11px] text-dim mono">{q.data?.events?.length ?? 0} shown · {q.data?.total ?? 0} total</span>
      </div>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b hairline text-left">
              {["Time", "Event ID", "Category", "Event", "Actor", "Workflow", "Entity", "Txn", "Outcome"].map((h) => <th key={h} className="px-3 py-2 label-xs font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {(q.data?.events ?? []).map((e: any) => (
              <Fragment key={e.event_id}>
                <tr className="border-b hairline hover:bg-white/[0.02] cursor-pointer" onClick={() => setOpen(open === e.event_id ? null : e.event_id)}>
                  <td className="px-3 py-1.5 mono text-dim whitespace-nowrap">{localTime(e.occurred_at, true)}</td>
                  <td className="px-3 py-1.5 mono text-dim">{e.event_id}</td>
                  <td className="px-3 py-1.5 text-muted whitespace-nowrap">{cat(e)}</td>
                  <td className="px-3 py-1.5 mono">{e.event_type}</td>
                  <td className="px-3 py-1.5 text-muted truncate max-w-[160px]">{e.actor}</td>
                  <td className="px-3 py-1.5 text-muted">{e.module}</td>
                  <td className="px-3 py-1.5 mono truncate max-w-[150px]">{e.entity_id}</td>
                  <td className="px-3 py-1.5 mono text-dim truncate max-w-[120px]">{e.txn_id}</td>
                  <td className="px-3 py-1.5">{e.result ? <Chip status={e.result} size="xs" /> : <span className="text-dim">—</span>}</td>
                </tr>
                {open === e.event_id && (
                  <tr className="border-b hairline bg-black/20">
                    <td colSpan={9} className="px-4 py-2.5 text-[11.5px]">
                      {e.reason && <div><span className="text-dim">Reason:</span> {e.reason}</div>}
                      {e.old_state && <div className="mono text-[10.5px] text-muted break-all"><span className="text-dim">Before:</span> {e.old_state}</div>}
                      {e.new_state && <div className="mono text-[10.5px] text-muted break-all"><span className="text-dim">After:</span> {e.new_state}</div>}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
