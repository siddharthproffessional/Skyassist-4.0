"use client";
import { Chip, KV } from "@/components/ui/primitives";
import ApprovalCard, { ResultNote } from "./ApprovalCard";
import type { ApprovalItem } from "@/lib/types";

/** U-4.1 — vulnerable first, then independent batches of ten. */
export function U41View({ r, approvals }: { r: any; approvals: ApprovalItem[] }) {
  const rep = r.report;
  const esc = approvals.filter((a) => a.kind === "batch" && a.status === "ESCALATED");
  return (
    <div>
      <div className="text-[13px] mb-3">
        {rep.escalated.length
          ? <span className="text-amber">Batch {rep.batches.find((b: any) => b.status === "ESCALATED")?.seq} failed. Previous successful batches were preserved.</span>
          : <span className="text-green">All batches committed.</span>}
        <span className="text-muted"> {rep.committed_passengers}/{rep.total} passengers committed; {rep.vulnerable} vulnerable passengers first, in their own transaction.</span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {rep.batches.map((b: any) => {
          const ok = b.status === "COMMITTED";
          const color = ok ? "#34d399" : b.status === "ESCALATED" ? "#f25f5c" : "#f5b544";
          return (
            <div key={b.batch_id} className="rounded-lg p-2.5 ring-1" style={{ background: `${color}14`, boxShadow: `inset 0 0 0 1px ${color}55` }}>
              <div className="label-xs" style={{ color }}>{b.kind === "PRIORITY" ? "PRIORITY · VULNERABLE" : `BATCH ${b.seq}`}</div>
              <div className="mono text-[18px] font-semibold">{b.passenger_count} pax</div>
              <Chip status={b.status} size="xs" />
              <div className="text-[10px] text-dim mt-1 mono">attempts {b.attempts}</div>
              {b.last_error && <div className="text-[10px] text-red mt-1 leading-tight line-clamp-3">{b.last_error}</div>}
            </div>
          );
        })}
      </div>
      <div className="text-[10.5px] text-dim mt-2">Each block is a separate database transaction. A failed batch rolls back only itself; earlier commits are never undone. Seat conflict injected as a labelled SYNTHETIC fault.</div>
      {esc.map((a) => <div key={a.id} className="mt-3"><ApprovalCard item={a} compact /></div>)}
    </div>
  );
}

/** U-4.2 — crew duty legality. */
export function U42View({ r, approvals }: { r: any; approvals: ApprovalItem[] }) {
  const c = r.results.find((x: any) => x.verdict !== "LEGAL") ?? r.results[0];
  const props = approvals.filter((a) => a.kind === "crew" && a.flight === "SA-700");
  return (
    <div>
      {r.departure_blocked && (
        <div className="rounded-lg bg-red/10 ring-1 ring-red/40 px-3 py-2.5 text-red font-semibold text-[13px] tracking-wide">
          ■ DEPARTURE BLOCKED — CURRENT CREW NOT LEGALLY AVAILABLE
        </div>
      )}
      <div className="grid sm:grid-cols-3 gap-3 mt-3">
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Remaining duty</div>
          <div className="mono text-[26px] font-semibold text-red">{c.remaining_min} min</div>
        </div>
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Required for operation</div>
          <div className="mono text-[26px] font-semibold">{c.required_min} min</div>
        </div>
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Duty counters</div>
          <div className="text-[14px] font-semibold text-green mt-1">{r.duty_counters_unchanged ? "✓ unchanged by the message" : "CHANGED"}</div>
        </div>
      </div>
      <div className="mt-3 text-[12px]">
        <div className="label-xs mb-1">Crew-channel message (stored as untrusted data)</div>
        <div className="rounded-lg bg-black/25 ring-1 ring-line px-3 py-2 italic text-muted">“{r.message ? "The crew is happy to extend duty, push the departure." : "—"}”
          {r.message?.flags?.length > 0 && <span className="not-italic ml-2"><Chip status="FLAGGED" label={`flags: ${r.message.flags.join(", ")}`} tone="amber" size="xs" /></span>}
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-x-6 mt-3">
        <div>
          <div className="label-xs mb-1">Current crew</div>
          {r.results.map((x: any) => <KV key={x.crew_id} k={x.crew_id} v={<Chip status={x.verdict} size="xs" />} />)}
        </div>
        <div>
          <div className="label-xs mb-1">Reserve search (deterministic)</div>
          {r.reserve_search.flatMap((s: any) => s.evaluated).map((e: any) => (
            <KV key={e.crew_id} k={e.crew_id} v={<Chip status={e.verdict} size="xs" />} />
          ))}
        </div>
      </div>
      {props.map((a) => <div key={a.id} className="mt-3"><ApprovalCard item={a} compact /></div>)}
    </div>
  );
}

function SignoffCard({ s, dep }: { s: any; dep: any }) {
  const ok = s.status === "VALID";
  const check = (name: string) => s.checks?.find((c: any) => c.check?.toLowerCase().includes(name));
  return (
    <div className={`rounded-xl p-3.5 ring-1 ${ok ? "bg-green/10 ring-green/40" : "bg-red/10 ring-red/40"}`}>
      <div className={`font-semibold text-[13px] tracking-wide ${ok ? "text-green" : "text-red"}`}>
        {ok ? "✓ GREEN — SIGN-OFF VALIDATED" : "■ RED — INVALID — DEPARTURE BLOCKED"}
      </div>
      <div className="text-[12px] mt-1">{ok ? "Sign-off validated. Final aircraft release stays with authorised maintenance staff." : "The engineer's sign-off could not be verified. Departure remains blocked."}</div>
      <div className="grid grid-cols-2 gap-x-6 mt-2">
        <KV k="Aircraft" v="A6-SKB" mono />
        <KV k="Defect" v="DEF-HYD-1 · hydraulic" mono />
        <KV k="Engineer" v={check("engineer exists")?.detail} mono />
        <KV k="Sign-off" v={s.signoff_id} mono />
        <KV k="Licence" v={check("licence valid")?.detail ?? "—"} />
        <KV k="Type rating" v={check("aircraft-type")?.detail ?? "—"} />
      </div>
      <div className="mt-2 text-[11px]">
        {(s.checks ?? []).map((c: any, i: number) => (
          <div key={i} className={c.passed === false ? "text-red" : "text-green/90"}>
            {c.passed === false ? "✕" : "✓"} {c.check}: <span className="text-muted">{c.detail}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 text-[11.5px]">Departure SA-710: <Chip status={dep?.blocked ? "BLOCKED" : "OK"} label={dep?.label} size="xs" /></div>
    </div>
  );
}

/** U-4.3 — maintenance sign-off. */
export function U43View({ invalid, valid }: { invalid?: any; valid?: any }) {
  return (
    <div className="grid grid-cols-1 gap-3">
      {invalid && <SignoffCard s={invalid.invalid} dep={invalid.status_after_invalid} />}
      {valid && <SignoffCard s={valid.valid} dep={valid.status_after_valid} />}
    </div>
  );
}

/** U-4.4 — passenger route vs baggage route, one transaction. */
export function U44View({ r }: { r: any }) {
  const p = r.plan;
  const ok = r.result?.status === "COMMITTED";
  return (
    <div>
      <div className="grid sm:grid-cols-3 gap-3">
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Passenger connection</div>
          <div className="mono text-[24px] font-semibold text-cyan">{p.connection_min} min</div>
          <div className="text-[11px] text-muted">walk {p.passenger?.transfer_min} min · feasible <Chip status={p.passenger_feasible ? "OK" : "FAIL"} size="xs" /></div>
        </div>
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Minimum bag transfer</div>
          <div className="mono text-[24px] font-semibold text-amber">{p.min_bag_transfer_min} min</div>
          <div className="text-[11px] text-muted">{p.bag_rule_source}</div>
        </div>
        <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-3">
          <div className="label-xs">Decision</div>
          <div className="text-[14px] font-semibold mt-1">{p.decision === "SEPARATE_FLIGHT" ? `Bags on ${p.bag_flight}` : p.decision}</div>
          <div className="text-[11px] text-muted">{p.delivery_note?.expected_arrival}</div>
        </div>
      </div>
      <div className="mt-3 grid sm:grid-cols-2 gap-3 text-[12px]">
        <div className="rounded-lg ring-1 ring-cyan/30 bg-cyan/5 p-3">
          <div className="label-xs text-cyan">Passenger route</div>
          SA-590 (B10) → <b className="mono">{p.candidate_flight}</b> · seat {r.result?.seat ?? "—"}
        </div>
        <div className="rounded-lg ring-1 ring-amber/40 bg-amber/5 p-3">
          <div className="label-xs text-amber">Baggage route (separate)</div>
          B10 → transfer sortation → <b className="mono">{p.bag_flight}</b> · {p.bags?.join(", ")}
        </div>
      </div>
      {r.injected && (
        <div className="mt-3 text-[12px] rounded-lg bg-white/5 ring-1 ring-line-2 p-2.5">
          Injected failure <span className="mono">{r.injected.txn_id}</span>: <Chip status={r.injected.status} size="xs" /> — seat, booking and bags rolled back together.
        </div>
      )}
      <div className={`mt-3 text-[12px] rounded-lg p-2.5 ring-1 ${ok ? "bg-green/10 ring-green/30" : "bg-red/10 ring-red/30"}`}>
        {ok ? <>Seat + booking + bag plan + delivery note committed in <b>one</b> transaction <span className="mono">{r.result.txn_id}</span>.</> : <>Not committed: {r.result?.reason}</>}
      </div>
      {r.result?.passenger_message && <div className="mt-2 text-[11.5px] text-muted">Passenger message: “{r.result.passenger_message}”</div>}
    </div>
  );
}

/** U-4.5 — stale approval stepper. All decisions are real controller actions. */
export function U45View({ status, approvals, onConflict, conflictBusy, lastExec }: {
  status: any; approvals: ApprovalItem[]; onConflict: () => void; conflictBusy: boolean; lastExec?: any;
}) {
  const ek = approvals.filter((a) => a.kind === "gate" && a.flight === "EK-812").sort((a, b) => String(a.requested_at).localeCompare(String(b.requested_at)));
  const first = ek[0];
  const conflictDone = !!status?.approvals?.length && approvals.some((a) => a.kind === "gate" && a.status === "STALE") || !!lastExec;
  const steps = [
    { k: "Stage", done: !!first, text: first ? `Gate agent staged ${first.id}: EK-812 → B07 (versions recorded)` : "Run the scenario to stage the move." },
    { k: "Approve", done: first && first.status !== "PENDING", text: "Controller approves the exact snapshot." },
    { k: "Conflict", done: conflictDone, text: "SIMULATION: ramp control gives B07 to SA-880 (versioned state change)." },
    { k: "Execute", done: first && ["STALE", "EXECUTED"].includes(first.status), text: "Execution re-reads versions → mismatch → refused, STALE, fresh proposal." },
    { k: "Fresh decision", done: ek.some((a) => a.status === "EXECUTED"), text: "Controller approves and executes the new proposal on the new state." },
  ];
  return (
    <div>
      <ol className="flex flex-wrap gap-2 mb-3">
        {steps.map((s, i) => (
          <li key={s.k} className={`flex-1 min-w-[150px] rounded-lg p-2.5 ring-1 ${s.done ? "ring-green/40 bg-green/5" : "ring-line-2 bg-white/[0.02]"}`}>
            <div className="label-xs" style={{ color: s.done ? "#34d399" : undefined }}>{i + 1} · {s.k} {s.done ? "✓" : ""}</div>
            <div className="text-[11px] text-muted leading-snug mt-0.5">{s.text}</div>
          </li>
        ))}
      </ol>
      {first && first.status === "APPROVED" && !conflictDone && (
        <button onClick={onConflict} disabled={conflictBusy}
          className="mb-3 text-[12px] px-3 py-2 rounded-lg bg-violet/15 text-violet ring-1 ring-violet/40 hover:bg-violet/25">
          ◆ Simulation event: another flight (SA-880) takes Gate B07
        </button>
      )}
      {lastExec && <ResultNote r={lastExec} />}
      {ek.filter((a) => a.status === "STALE").map((a) => (
        <div key={a.id} className="rounded-lg bg-red/10 ring-1 ring-red/40 p-3 text-[12px] mb-2">
          <div className="font-semibold text-red">Execution refused — {a.id} marked STALE</div>
          <div className="mt-1">Another flight took Gate B07. The previous approval is no longer valid.</div>
          <div className="mt-1 text-muted mono text-[11px] break-words">{a.validations_failed[0]}</div>
          {a.superseded_by && <div className="mt-1 text-amber">Fresh proposal {a.superseded_by} staged — the controller must approve the new state.</div>}
        </div>
      ))}
      <div className="flex flex-col gap-3 mt-3">
        {ek.filter((a) => ["PENDING", "APPROVED"].includes(a.status)).map((a) => <ApprovalCard key={a.id} item={a} compact />)}
        {ek.filter((a) => !["PENDING", "APPROVED"].includes(a.status)).map((a) => (
          <div key={a.id} className="text-[11.5px] flex items-center gap-2">
            <span className="mono">{a.id}</span><Chip status={a.status} size="xs" />
            <span className="text-muted truncate">{a.status === "STALE" ? "Another flight took Gate B07. The previous approval is no longer valid." : a.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
