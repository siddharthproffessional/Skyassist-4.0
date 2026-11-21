"use client";
import Link from "next/link";
import { useState } from "react";
import { useFlight, useGate, useRoutes } from "@/lib/hooks";
import { useTwin } from "@/lib/store";
import { Chip, KV } from "@/components/ui/primitives";
import { GATE_LABEL } from "@/lib/colors";
import { localTime } from "@/lib/format";

function Q({ n, q, children }: { n: number; q: string; children: React.ReactNode }) {
  return (
    <div className="py-2 border-t hairline first:border-t-0">
      <div className="label-xs mb-1"><span className="text-cyan mr-1">{n}</span>{q}</div>
      <div className="text-[12px] leading-snug">{children}</div>
    </div>
  );
}

function Details({ children, label = "Technical details" }: { children: React.ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button className="text-[11px] text-cyan hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "▾" : "▸"} {label}
      </button>
      {open && <div className="mt-1.5 rounded-lg bg-black/25 ring-1 ring-line p-2.5 text-[11px]">{children}</div>}
    </div>
  );
}

export function FlightPanel({ no }: { no: string }) {
  const q = useFlight(no);
  const routes = useRoutes(no);
  const setFocus = useTwin((s) => s.setFocusRoute);
  const focus = useTwin((s) => s.focusRoute);
  const d = q.data;
  if (q.isLoading) return <div className="p-4 text-dim text-sm">Loading {no}…</div>;
  if (!d) return <div className="p-4 text-red text-sm">{no}: not found in flight data.</div>;
  const f = d.flight;
  const pendingGate = d.gate_approvals.filter((a: any) => ["PENDING", "APPROVED"].includes(a.status));
  const pendingJ = d.journey_approvals.filter((a: any) => a.status === "PENDING");
  const pendingC = d.crew_proposals.filter((a: any) => a.status === "PENDING_APPROVAL");
  const anyPending = pendingGate.length + pendingJ.length + pendingC.length;
  const sepBags = d.bags.filter((b: any) => b.kind === "SEPARATE");
  return (
    <div className="px-3.5 pb-3">
      <div className="flex items-start justify-between gap-2 pt-4">
        <div>
          <div className="mono text-[22px] font-semibold leading-none">{f.flight_no}</div>
          <div className="text-[12px] text-muted mt-1">{f.origin} → {f.destination} · {f.direction.toLowerCase()}</div>
        </div>
        <Chip status={f.status === "CANCELLED" ? "CANCELLED" : f.holds.length ? "BLOCKED" : f.status} />
      </div>
      <div className="grid grid-cols-3 gap-2 my-3 text-center">
        {[["Gate", f.gate ?? "—"], ["Sched", f.sched], ["Est.", f.est ?? "—"]].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-white/[0.03] ring-1 ring-line py-1.5">
            <div className="label-xs">{k}</div><div className="mono text-[14px] font-semibold">{v}</div>
          </div>
        ))}
      </div>
      <Q n={1} q="What happened?">
        {f.health === "normal" ? "Operating normally." : f.reasons.join(" · ")}
        {f.previous_gate && f.status === "GATE_CHANGED" && <> Gate changed from <b className="mono">{f.previous_gate}</b> to <b className="mono">{f.gate}</b>.</>}
      </Q>
      <Q n={2} q="Who is affected?">
        {d.passenger_count} booking(s) on this flight
        {d.vulnerable_count > 0 && <>, <b className="text-amber">{d.vulnerable_count} vulnerable</b> (recorded needs)</>}.
        {d.rebooked_out.length > 0 && <> {d.rebooked_out.length} already rebooked away.</>}
        {d.rebooked_in.length > 0 && <> {d.rebooked_in.length} rebooked onto this flight.</>}
        {sepBags.length > 0 && <div className="text-amber mt-1">{sepBags.length} bag(s) assigned here travel separately from their passengers.</div>}
      </Q>
      <Q n={3} q="What is SkyAssist doing?">
        {d.rebooking_jobs.length > 0 && d.rebooking_jobs.map((j: any) => (
          <div key={j.job_id}>Rebooking job <span className="mono">{j.job_id}</span>: <Chip status={j.status} size="xs" /></div>
        ))}
        {d.departure && <div>Departure check: <Chip status={d.departure.blocked ? "BLOCKED" : "OK"} label={d.departure.label} size="xs" /></div>}
        {d.crew.length > 0 && d.crew.map((c: any) => (
          <div key={c.crew_id} className="flex items-center gap-1.5">
            <span className="mono text-[11px]">{c.crew_id}</span> {c.name}
            {c.verdict && <Chip status={c.verdict} size="xs" />}
            {c.remaining_min != null && <span className="text-[10.5px] text-dim">{c.remaining_min}/{c.required_min} min</span>}
          </div>
        ))}
        {!d.rebooking_jobs.length && !d.departure && !d.crew.length && <span className="text-dim">No agent activity recorded for this flight.</span>}
      </Q>
      <Q n={4} q="Is human approval required?">
        {anyPending ? (
          <div className="flex items-center justify-between gap-2">
            <span className="text-amber">{anyPending} decision(s) waiting for a controller.</span>
            <Link href="/approvals/" className="text-cyan text-[11.5px] hover:underline">Open Approval Centre →</Link>
          </div>
        ) : <span className="text-dim">No pending decision.</span>}
      </Q>
      <Q n={5} q="What happened next?">
        {d.gate_approvals.filter((a: any) => !["PENDING", "APPROVED"].includes(a.status)).slice(0, 3).map((a: any) => (
          <div key={a.approval_id}><span className="mono text-[11px]">{a.approval_id}</span> <Chip status={a.status} size="xs" /></div>
        ))}
        {d.signoffs.slice(-2).map((s: any) => (
          <div key={s.signoff_id}>Sign-off <span className="mono">{s.engineer_id}</span>: <Chip status={s.validation_status}
            label={s.validation_status === "VALID" ? "SIGN-OFF VALIDATED" : "INVALID — DEPARTURE BLOCKED"} size="xs" /></div>
        ))}
        {d.journey_approvals.filter((a: any) => a.status !== "PENDING").map((a: any) => (
          <div key={a.approval_id}><span className="mono text-[11px]">{a.approval_id}</span> <Chip status={a.status} size="xs" /></div>
        ))}
        {!d.gate_approvals.length && !d.signoffs.length && !d.journey_approvals.length && <span className="text-dim">Nothing yet.</span>}
      </Q>
      {routes.data?.routes?.some((r) => r.ok) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {routes.data.routes.filter((r) => r.ok).slice(0, 4).map((r, i) => {
            const on = focus && focus.join() === r.node_path!.join();
            return (
              <button key={i} onClick={() => setFocus(on ? null : r.node_path!)}
                className={`text-[11px] px-2 py-1 rounded-md ring-1 ${on ? "ring-cyan text-cyan bg-cyan/10" : "ring-line-2 text-muted hover:text-text"}`}>
                Route {r.from}→{r.to} · {Math.round(r.distance_m!)} m · {r.walk_min} min{r.profile !== "STANDARD" ? " · step-free" : ""}
              </button>
            );
          })}
        </div>
      )}
      <Details>
        <KV k="Aircraft" v={f.aircraft_reg} mono />
        <KV k="Boarding close" v={f.boarding_close} mono />
        {d.seats && <KV k="Seats free" v={`${d.seats.free}/${d.seats.total}`} mono />}
        {d.bag_capacity && <KV k="Bag capacity" v={`${d.bag_capacity.used}/${d.bag_capacity.capacity}`} mono />}
        {d.defects.map((x: any) => <KV key={x.defect_id} k={x.defect_id} v={`${x.defect_type} · ${x.status} · ${x.restriction}`} />)}
        {d.signoffs.map((s: any) => (
          <div key={s.signoff_id} className="mt-1.5">
            <div className="mono">{s.signoff_id} · {s.engineer_id} · signed {s.signed_at_utc}</div>
            {(s.reasons_list ?? []).map((r: string, i: number) => <div key={i} className="text-red">• {r}</div>)}
          </div>
        ))}
        <div className="text-dim mt-2">{d.label}</div>
      </Details>
    </div>
  );
}

export function GatePanel({ gate }: { gate: string }) {
  const q = useGate(gate);
  const select = useTwin((s) => s.select);
  const g = q.data;
  if (q.isLoading) return <div className="p-4 text-dim text-sm">Loading gate {gate}…</div>;
  if (!g) return <div className="p-4 text-red text-sm">Unknown gate.</div>;
  const flights = [...g.departures, ...g.arrivals];
  return (
    <div className="px-3.5 pb-3">
      <div className="flex items-start justify-between gap-2 pt-4">
        <div>
          <div className="mono text-[22px] font-semibold leading-none">Gate {g.gate}</div>
          <div className="text-[12px] text-muted mt-1">Concourse {g.concourse} · resource version v{g.version}</div>
        </div>
        <Chip status={g.status} label={GATE_LABEL[g.status as keyof typeof GATE_LABEL].toUpperCase()} />
      </div>
      <Q n={1} q="Assigned flights">
        {flights.length ? flights.map((f: string) => (
          <button key={f} className="mono text-cyan hover:underline mr-2" onClick={() => select({ kind: "flight", id: f })}>{f}</button>
        )) : <span className="text-dim">No flight assigned — available.</span>}
        {g.cancelled.length > 0 && <div className="text-red">Cancelled here: {g.cancelled.join(", ")}</div>}
        {g.gate_changed_away.length > 0 && <div className="text-amber">Previous gate of {g.gate_changed_away.join(", ")} (gate change)</div>}
      </Q>
      <Q n={2} q="Pending gate changes">
        {g.pending_approvals.length ? g.pending_approvals.map((a: any) => (
          <div key={a.approval_id}><span className="mono">{a.approval_id}</span> {a.flight_no} → {g.gate} <Chip status={a.status} size="xs" /></div>
        )) : <span className="text-dim">None.</span>}
      </Q>
      <Q n={3} q="Conflicts">
        {g.conflicts.length ? g.conflicts.map((a: any) => (
          <div key={a.approval_id} className="text-red">
            <span className="mono">{a.approval_id}</span> STALE — Another flight took Gate {g.gate}. The previous approval is no longer valid.
          </div>
        )) : <span className="text-dim">No conflicts.</span>}
      </Q>
      <Details label="Gate history (audit)">
        {g.history.length === 0 && <div className="text-dim">No gate events.</div>}
        {g.history.map((h: any) => (
          <div key={h.event_id} className="flex gap-2 py-0.5">
            <span className="mono text-dim">{localTime(h.occurred_at, true)}</span>
            <span className="mono">{h.event_type}</span>
            <span className="text-muted truncate">{h.entity_id}</span>
          </div>
        ))}
        <div className="text-dim mt-2">{g.label}</div>
      </Details>
    </div>
  );
}

export default function EntityPanel() {
  const sel = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  if (!sel) return null;
  return (
    <div className="relative">
      <button className="absolute right-2 -top-1.5 z-10 text-dim hover:text-text text-[12px] px-1.5" onClick={() => select(null)} aria-label="Close details">✕ close</button>
      {sel.kind === "flight" ? <FlightPanel no={sel.id} /> : <GatePanel gate={sel.id} />}
    </div>
  );
}
