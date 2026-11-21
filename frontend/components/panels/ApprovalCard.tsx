"use client";
import { useEffect, useState } from "react";
import type { ApprovalItem } from "@/lib/types";
import { useAction } from "@/lib/hooks";
import { Btn, Chip, ErrorNote } from "@/components/ui/primitives";
import { localTime, minutesLeft } from "@/lib/format";

const KIND_LABEL: Record<string, string> = {
  gate: "Gate move", journey: "Paused risky action", crew: "Crew assignment", batch: "Escalated batch", assistance: "Passenger assistance",
};

function Countdown({ iso }: { iso: string | null }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => tick((x) => x + 1), 15000);
    return () => clearInterval(i);
  }, []);
  if (!iso) return <span className="text-dim">no expiry</span>;
  const m = minutesLeft(iso)!;
  return <span className={m <= 3 ? "text-red" : "text-amber"}>{m > 0 ? `expires in ${m} min` : "expired"} ({localTime(iso)})</span>;
}

export default function ApprovalCard({ item, onResult, compact = false }: { item: ApprovalItem; onResult?: (r: any) => void; compact?: boolean }) {
  const approve = useAction((v) => `/web/approvals/${item.kind}/${item.id}/approve`);
  const decline = useAction((v) => `/web/approvals/${item.kind}/${item.id}/decline`);
  const reassess = useAction((v) => `/web/approvals/${item.kind}/${item.id}/reassess`);
  const execute = useAction(() => `/web/approvals/gate/${item.id}/execute`);
  const [result, setResult] = useState<any>(null);
  const pending = ["PENDING", "PENDING_APPROVAL", "ESCALATED"].includes(item.status);
  const err = approve.error || decline.error || reassess.error || execute.error;
  const busy = approve.isPending || decline.isPending || reassess.isPending || execute.isPending;
  const done = (r: any) => { setResult(r); onResult?.(r); };

  return (
    <article className={`glass rounded-xl p-4 ${pending ? "ring-1 ring-amber/30" : item.can_execute ? "ring-1 ring-green/30" : ""}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="label-xs">{KIND_LABEL[item.kind]} · <span className="mono normal-case tracking-normal">{item.id}</span></div>
          <h3 className="text-[15px] font-semibold mt-1 leading-snug">{item.title}</h3>
        </div>
        <Chip status={item.status} />
      </header>
      <div className={`grid ${compact ? "grid-cols-1" : "md:grid-cols-2"} gap-x-6 gap-y-2.5 mt-3 text-[12px]`}>
        <div><div className="label-xs mb-0.5">AI recommendation</div>{item.recommendation}</div>
        <div><div className="label-xs mb-0.5">Why</div><span className="text-muted">{item.why}</span></div>
        <div>
          <div className="label-xs mb-0.5">Python validations</div>
          {item.validations_passed.map((v, i) => <div key={i} className="text-green/90">✓ {v}</div>)}
          {item.validations_failed.filter(Boolean).map((v, i) => <div key={i} className="text-red/90">✕ {v}</div>)}
          {!item.validations_passed.length && !item.validations_failed.length && <span className="text-dim">—</span>}
        </div>
        <div><div className="label-xs mb-0.5">What will change</div><span className="text-muted">{item.state_change}</span></div>
        {item.risks && <div><div className="label-xs mb-0.5">Risks</div><span className="text-muted">{item.risks}</span></div>}
        <div><div className="label-xs mb-0.5">If declined</div><span className="text-muted">{item.if_declined}</span></div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-dim">
        <span>Policy: {item.policy}</span>
        {pending && <Countdown iso={item.expires_at} />}
        {item.state_version && <span className="mono">state {typeof item.state_version === "string" ? item.state_version : JSON.stringify(item.state_version)}</span>}
        {item.snapshot_hash && <span className="mono">snapshot {item.snapshot_hash.slice(0, 12)}…</span>}
        {item.parent_id && <span>re-staged from <span className="mono">{item.parent_id}</span></span>}
        {item.decided_by && <span>decided by {item.decided_by}</span>}
      </div>
      {(pending || item.can_execute) && (
        <div className="mt-3.5 flex flex-wrap gap-2">
          {pending && (
            <>
              <Btn tone="approve" size="lg" disabled={busy}
                onClick={() => approve.mutate({ body: { snapshot_hash: item.snapshot_hash ?? undefined } }, { onSuccess: done })}>
                {item.kind === "batch" ? "APPROVE RETRY" : "APPROVE"}
              </Btn>
              {item.kind !== "batch" && (
                <Btn tone="decline" size="lg" disabled={busy} onClick={() => decline.mutate({ body: {} }, { onSuccess: done })}>DECLINE</Btn>
              )}
              {["gate", "journey", "crew"].includes(item.kind) && (
                <Btn size="lg" disabled={busy} onClick={() => reassess.mutate({ body: {} }, { onSuccess: done })}>REQUEST REASSESSMENT</Btn>
              )}
            </>
          )}
          {item.can_execute && (
            <Btn tone="primary" size="lg" disabled={busy} onClick={() => execute.mutate({}, { onSuccess: done })}
              title="Execution re-checks the reviewed state versions (compare-and-set)">
              EXECUTE APPROVED MOVE
            </Btn>
          )}
        </div>
      )}
      <div className="mt-2"><ErrorNote error={err} /></div>
      {result && <ResultNote r={result} />}
    </article>
  );
}

export function ResultNote({ r }: { r: any }) {
  if (!r) return null;
  if (r.status === "STALE") {
    return (
      <div className="mt-2 rounded-lg bg-red/10 ring-1 ring-red/30 p-3 text-[12px]">
        <div className="font-semibold text-red">Execution refused — approval marked STALE</div>
        <div className="mt-1">Another flight took the gate. The previous approval is no longer valid.</div>
        <ul className="mt-1 text-muted mono text-[11px]">{(r.problems ?? []).map((p: string, i: number) => <li key={i}>• {p}</li>)}</ul>
        {r.new_approval_id && <div className="mt-1 text-amber">A fresh proposal {r.new_approval_id} was staged — it needs a new controller decision.</div>}
      </div>
    );
  }
  const ok = /EXECUTED|APPROVED|COMMITTED|REJECTED|reassessed/i.test(JSON.stringify(r.status ?? r.reassessed ?? ""));
  return (
    <div className={`mt-2 rounded-lg p-3 text-[12px] ring-1 ${ok ? "bg-green/10 ring-green/30" : "bg-white/5 ring-line-2"}`}>
      <span className="font-semibold">{r.status ?? (r.reassessed ? "Reassessed against current state" : "Done")}</span>
      {r.to && <> — moved {r.flight} from {r.from} to {r.to}.</>}
      {r.fresh_validation && <span className="text-muted"> Fresh result: {r.fresh_validation.decision ?? r.fresh_validation.verdict}</span>}
      {r.new_item && <span className="text-amber"> New proposal {r.new_item.id} staged.</span>}
    </div>
  );
}
