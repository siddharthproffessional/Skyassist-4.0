"use client";
import Link from "next/link";
import type { Mission, TwinState } from "@/lib/types";
import { Chip } from "@/components/ui/primitives";

/** The five questions every screen answers, computed from backend state only. */
export default function Situation({ s, mission }: { s: TwinState; mission?: Mission }) {
  const crit = s.flights.filter((f) => f.health === "critical");
  const k = s.kpis;
  const lastDone = s.events.find((e) => /COMMITTED|EXECUTED|GRANTED|VALID|STALE|REFUSED|ROLLED_BACK|BLOCKED/.test(`${e.result} ${e.event_type}`));
  const rows: [string, React.ReactNode][] = [
    ["What happened?", crit.length
      ? <>{crit.slice(0, 3).map((f) => <span key={f.flight_no} className="mono">{f.flight_no} <span className="text-red">{f.status === "CANCELLED" ? "cancelled" : "blocked"}</span>{" "}</span>)}{crit.length > 3 ? `+${crit.length - 3} more` : ""}</>
      : <span className="text-green">No critical disruption.</span>],
    ["Who is affected?", <>{k.affected_passengers} passengers on disrupted departures · {k.rebooked_passengers} rebooked</>],
    ["What is the AI doing?", mission ? <><span className="text-violet">{mission.kind}</span> — {mission.summary || mission.title} <Chip status={mission.status} size="xs" /></> : <span className="text-dim">No mission recorded yet in this dataset.</span>],
    ["Is approval required?", k.pending_approvals
      ? <Link href="/approvals/" className="text-amber hover:underline">{k.pending_approvals} decision(s) waiting for a controller →</Link>
      : <span className="text-dim">No pending decision.</span>],
    ["What happened next?", lastDone ? <><span className="mono text-[11px]">{lastDone.event_type}</span> <span className="text-muted">{lastDone.entity_id}</span></> : <span className="text-dim">—</span>],
  ];
  return (
    <dl className="px-3.5 pb-2">
      {rows.map(([q, a], i) => (
        <div key={q} className="py-1.5 border-t hairline first:border-t-0">
          <dt className="label-xs"><span className="text-cyan mr-1">{i + 1}</span>{q}</dt>
          <dd className="text-[12px] leading-snug mt-0.5">{a}</dd>
        </div>
      ))}
    </dl>
  );
}
