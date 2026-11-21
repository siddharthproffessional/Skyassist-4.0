"use client";
import { useState } from "react";
import PageShell from "@/components/shell/PageShell";
import ApprovalCard from "@/components/panels/ApprovalCard";
import { Chip } from "@/components/ui/primitives";
import { useApprovals } from "@/lib/hooks";
import { localTime } from "@/lib/format";

const PENDING = ["PENDING", "PENDING_APPROVAL", "ESCALATED"];

export default function ApprovalsPage() {
  const q = useApprovals();
  const [kind, setKind] = useState<string>("all");
  const items = (q.data?.items ?? []).filter((i) => kind === "all" || i.kind === kind);
  const open = items.filter((i) => PENDING.includes(i.status) || i.can_execute);
  const closed = items.filter((i) => !PENDING.includes(i.status) && !i.can_execute);
  return (
    <PageShell title="Approval Centre"
      subtitle="Every proposal is bound to the exact action and state snapshot the controller reviewed. Expiry produces no operational change. Each workflow keeps its own policy: gate moves 30 min, Round 3 paused actions 15 min, passenger assistance escalates after 90 s.">
      <div className="flex gap-1.5 mb-4">
        {["all", "gate", "journey", "crew", "batch", "assistance"].map((k) => (
          <button key={k} onClick={() => setKind(k)}
            className={`px-3 py-1.5 rounded-lg text-[12px] ring-1 ${kind === k ? "ring-cyan text-cyan bg-cyan/10" : "ring-line-2 text-muted hover:text-text"}`}>
            {k === "all" ? "All" : k[0].toUpperCase() + k.slice(1)}
          </button>
        ))}
      </div>
      <h2 className="label-xs mb-2">Waiting for a decision · {open.length}</h2>
      {open.length === 0 && <div className="glass rounded-xl p-5 text-[12.5px] text-dim mb-6">Nothing is waiting. Agents stage proposals here — no agent can approve or execute.</div>}
      <div className="grid xl:grid-cols-2 gap-3 mb-8">
        {open.map((i) => <ApprovalCard key={`${i.kind}-${i.id}`} item={i} />)}
      </div>
      <h2 className="label-xs mb-2">Decided / closed · {closed.length}</h2>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-[12px]">
          <thead className="text-left text-dim">
            <tr className="border-b hairline">
              {["Kind", "ID", "Item", "Status", "Decided by", "Requested"].map((h) => <th key={h} className="px-3 py-2 font-medium label-xs">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {closed.map((i) => (
              <tr key={`${i.kind}-${i.id}`} className="border-b hairline last:border-0">
                <td className="px-3 py-2 text-muted">{i.kind}</td>
                <td className="px-3 py-2 mono">{i.id}</td>
                <td className="px-3 py-2">{i.title}{i.superseded_by ? <span className="text-amber"> → superseded by {i.superseded_by}</span> : null}</td>
                <td className="px-3 py-2"><Chip status={i.status} size="xs" /></td>
                <td className="px-3 py-2 text-muted">{i.decided_by ?? "—"}</td>
                <td className="px-3 py-2 mono text-dim">{localTime(i.requested_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
