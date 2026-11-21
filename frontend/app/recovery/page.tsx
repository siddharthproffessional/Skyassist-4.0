"use client";
import { useMemo, useState } from "react";
import PageShell from "@/components/shell/PageShell";
import TwinView from "@/components/twin/TwinView";
import MissionTimeline from "@/components/panels/MissionTimeline";
import { U41View, U42View, U43View, U44View, U45View } from "@/components/panels/ScenarioViews";
import { Btn, Chip, ErrorNote, Metric, Panel, SyntheticBadge } from "@/components/ui/primitives";
import { useAction, useApprovals, useBagLegs, useLayout, useMission, useRoutes, useScenarios, useTwinState } from "@/lib/hooks";
import { useTwin, type CameraPreset } from "@/lib/store";
import type { TwinState } from "@/lib/types";

type Ctl = { id: string; label: string; scenario?: string; gates: string[]; preset: CameraPreset; desc: string };
const CONTROLS: Ctl[] = [
  { id: "cancel", label: "Flight cancellation", scenario: "U-4.1", gates: ["C05", "C09", "C02"], preset: "C", desc: "SA-560 cancelled — 40 passengers to SA-562, vulnerable first" },
  { id: "seat", label: "Seat conflict", scenario: "U-4.1", gates: ["C05", "C09"], preset: "C", desc: "Batch 3 hits an external seat sale (labelled synthetic fault)" },
  { id: "crew", label: "Crew duty violation", scenario: "U-4.2", gates: ["A12"], preset: "A", desc: "Crew message tries to extend the captain's duty on SA-700" },
  { id: "maint", label: "Maintenance sign-off rejection", scenario: "U-4.3", gates: ["A16"], preset: "A", desc: "Unlicensed 'OK' on a hydraulic defect, then a valid replacement" },
  { id: "bags", label: "Baggage connection failure", scenario: "U-4.4", gates: ["B10", "B12", "B16", "B18"], preset: "B", desc: "35-min passenger connection vs 45-min bag minimum" },
  { id: "gate", label: "Gate conflict / stale approval", scenario: "U-4.5", gates: ["C03", "B07", "A05"], preset: "B", desc: "EK-812 → B07 approved, then B07 is taken by SA-880" },
  { id: "delay", label: "Flight delay", gates: ["B02"], preset: "B", desc: "SA-482 to MAN delayed +30 min (synthetic feed event)" },
  { id: "corridor", label: "Corridor closure", gates: ["C12", "B14"], preset: "routes", desc: "Skywalk B–C closed — routes recalculated (S1: C12 → B14)" },
];

function diff(before?: TwinState, after?: TwinState) {
  if (!before || !after) return [];
  const out: string[] = [];
  const bf = new Map(before.flights.map((f) => [f.flight_no, f]));
  after.flights.forEach((f) => {
    const b = bf.get(f.flight_no);
    if (!b) return;
    if (b.gate !== f.gate) out.push(`${f.flight_no}: gate ${b.gate} → ${f.gate}`);
    if (b.status !== f.status) out.push(`${f.flight_no}: ${b.status} → ${f.status}`);
    if (b.holds.length !== f.holds.length) out.push(`${f.flight_no}: departure ${f.holds.length ? "BLOCKED" : "hold cleared"}`);
    if (b.passengers !== f.passengers) out.push(`${f.flight_no}: ${b.passengers} → ${f.passengers} passengers`);
  });
  const bg = new Map(before.gates.map((g) => [g.gate, g]));
  after.gates.forEach((g) => {
    const b = bg.get(g.gate);
    if (b && b.status !== g.status) out.push(`Gate ${g.gate}: ${b.status} → ${g.status}`);
  });
  const bc = new Set(before.closed_edges.map((e) => e.edge_id));
  after.closed_edges.forEach((e) => !bc.has(e.edge_id) && out.push(`Corridor ${e.edge_id} CLOSED`));
  before.closed_edges.forEach((e) => !after.closed_edges.some((x) => x.edge_id === e.edge_id) && out.push(`Corridor ${e.edge_id} reopened`));
  return out;
}

export default function RecoveryPage() {
  const st = useTwinState();
  const layout = useLayout();
  const scen = useScenarios();
  const approvals = useApprovals();
  const [ctl, setCtl] = useState<Ctl>(CONTROLS[0]);
  const [before, setBefore] = useState<TwinState | undefined>();
  const [results, setResults] = useState<Record<string, any>>({});
  const [missionId, setMissionId] = useState<string | null>(null);
  const [corridor, setCorridor] = useState<any>(null);
  const [lastExec, setLastExec] = useState<any>(null);
  const mission = useMission(missionId);
  const routes = useRoutes(null);
  const legs = useBagLegs(null);
  const setPreset = useTwin((s) => s.setPreset);
  const setSimulate = useTwin((s) => s.setSimulate);
  const setFocus = useTwin((s) => s.setFocusRoute);
  const run = useAction((v) => `/web/scenarios/${v.code}/run`);
  const conflict = useAction("/web/scenarios/U-4.5/conflict");
  const reset = useAction("/web/scenarios/reset");
  const delay = useAction("/web/scenarios/delay");
  const close = useAction((v) => `/web/corridors/${v.edge}`);
  const execute = useAction((v) => `/web/approvals/gate/${v.id}/execute`);
  const status = useMemo(() => Object.fromEntries((scen.data?.scenarios ?? []).map((s: any) => [s.code, s])), [scen.data]);
  const m = scen.data?.metrics ?? {};
  const err = run.error || conflict.error || reset.error || delay.error || close.error;
  const busy = run.isPending || delay.isPending || close.isPending;

  const choose = (c: Ctl) => { setCtl(c); setPreset(c.preset); setFocus(null); };
  const snap = () => setBefore(st.data ? JSON.parse(JSON.stringify(st.data)) : undefined);
  const done = (key: string) => (r: any) => { setResults((x) => ({ ...x, [key]: r })); if (r?.mission_id) setMissionId(r.mission_id); setSimulate(true); };

  const trigger = () => {
    snap();
    if (ctl.id === "delay") return delay.mutate({ body: { flight_no: "SA-482", minutes: 30 } }, { onSuccess: done("delay") });
    if (ctl.id === "corridor") {
      const closed = st.data?.closed_edges.some((e) => e.edge_id === "E_SKY_BC");
      return close.mutate({ edge: "E_SKY_BC", body: { available: !!closed, reason: "SYNTHETIC: skywalk B–C closed for cleaning" } }, {
        onSuccess: (r: any) => { setCorridor(r); const a = r.affected_routes?.[0]?.after; setFocus(a?.ok ? a.node_path : null); setSimulate(true); },
      });
    }
    const code = ctl.scenario!;
    const body = code === "U-4.3" ? { phase: status["U-4.3"]?.invalid_submitted ? "valid" : "invalid" } : {};
    run.mutate({ code, body }, { onSuccess: done(code === "U-4.3" ? `U-4.3-${body.phase}` : code) });
  };

  const key = ctl.scenario ?? ctl.id;
  const ran = ctl.scenario ? status[ctl.scenario]?.done || (ctl.scenario === "U-4.3" && status["U-4.3"]?.invalid_submitted) : !!results[ctl.id] || (ctl.id === "corridor" && !!corridor);
  const label = ctl.id === "corridor" ? (st.data?.closed_edges.some((e) => e.edge_id === "E_SKY_BC") ? "Reopen Skywalk B–C" : "Close Skywalk B–C")
    : ctl.scenario === "U-4.3" && status["U-4.3"]?.invalid_submitted && !status["U-4.3"]?.done ? "Submit valid replacement sign-off"
    : ctl.scenario === "U-4.5" ? "Stage EK-812 → B07" : "Trigger scenario";
  const changes = diff(before, st.data);
  const items = approvals.data?.items ?? [];

  return (
    <PageShell title="Airport Recovery Simulator" full
      subtitle={<>Every control below runs a real backend operation on the synthetic dataset through the agents and Python services. <SyntheticBadge text="Synthetic scenario results" /></>}
      actions={<Btn tone="decline" disabled={reset.isPending} onClick={() => reset.mutate({}, { onSuccess: () => { setResults({}); setBefore(undefined); setMissionId(null); setCorridor(null); setLastExec(null); setFocus(null); } })}>Reset synthetic dataset</Btn>}>
      <div className="grid grid-cols-6 lg:grid-cols-11 gap-3 mb-3 glass rounded-xl px-4 py-3 shrink-0">
        <Metric label="Affected pax" value={m.affected_passengers ?? "—"} />
        <Metric label="Vulnerable first" value={m.vulnerable_prioritised ?? "—"} tone="amber" />
        <Metric label="Rebook txns" value={m.rebooking_transactions ?? "—"} />
        <Metric label="Batches OK" value={m.successful_batches ?? "—"} tone="green" />
        <Metric label="Batches failed" value={m.failed_batches ?? "—"} tone={m.failed_batches ? "red" : undefined} />
        <Metric label="Crew checks" value={m.crew_validations ?? "—"} />
        <Metric label="Maint. blocks" value={m.maintenance_blocks ?? "—"} tone={m.maintenance_blocks ? "red" : undefined} />
        <Metric label="Bag plans" value={m.baggage_plans ?? "—"} />
        <Metric label="Gate conflicts" value={m.gate_conflicts ?? "—"} tone={m.gate_conflicts ? "red" : undefined} />
        <Metric label="Pending" value={m.pending_approvals ?? "—"} tone={m.pending_approvals ? "amber" : undefined} />
        <Metric label="Actions done" value={m.completed_actions ?? "—"} tone="green" />
      </div>
      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[250px_1fr_420px] gap-3">
        <Panel title="Scenario controls" bodyClass="overflow-y-auto scroll-thin pb-2">
          {CONTROLS.map((c) => {
            const done = c.scenario ? status[c.scenario]?.done : c.id === "corridor" ? st.data?.closed_edges.some((e) => e.edge_id === "E_SKY_BC") : !!results[c.id];
            return (
              <button key={c.id} onClick={() => choose(c)}
                className={`w-full text-left px-3.5 py-2.5 border-t hairline ${ctl.id === c.id ? "bg-cyan/[0.08] shadow-[inset_3px_0_0_#3ec5ff]" : "hover:bg-white/[0.03]"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-medium">{c.label}</span>
                  {c.scenario && <span className="mono text-[10px] text-dim whitespace-nowrap">{c.scenario}</span>}
                </div>
                <div className="text-[10.5px] text-muted leading-snug mt-0.5">{c.desc}</div>
                {done && <div className="mt-1"><Chip status="DONE" label="RAN ON THIS DATASET" tone="green" size="xs" /></div>}
              </button>
            );
          })}
        </Panel>
        <div className="min-h-[420px] flex flex-col gap-3 min-w-0">
          <div className="grid grid-cols-2 gap-3 flex-1 min-h-0">
            <div className="glass rounded-xl overflow-hidden relative">
              <div className="absolute top-2 left-3 z-10 label-xs text-amber">Before recovery {before ? "· snapshot" : "· run a scenario"}</div>
              {before ? <TwinView state={before} layout={layout.data} compact toolbar={false} highlightGates={ctl.gates} />
                : <div className="h-full grid place-items-center text-[12px] text-dim p-6 text-center">The BEFORE view is a snapshot of backend state taken when you trigger a scenario.</div>}
            </div>
            <div className="glass rounded-xl overflow-hidden relative">
              <div className="absolute top-2 left-3 z-10 label-xs text-green">After recovery · live backend state</div>
              <TwinView state={st.data} layout={layout.data} routes={routes.data?.routes} legs={legs.data?.legs} toolbar={false} highlightGates={ctl.gates} />
            </div>
          </div>
          <div className="glass rounded-xl px-4 py-3 shrink-0 max-h-[150px] overflow-y-auto scroll-thin">
            <div className="label-xs mb-1">What changed (diff of backend snapshots)</div>
            {changes.length ? (
              <div className="flex flex-wrap gap-1.5">{changes.slice(0, 40).map((c, i) => <span key={i} className="mono text-[11px] px-2 py-0.5 rounded bg-white/5 ring-1 ring-line">{c}</span>)}</div>
            ) : <div className="text-[12px] text-dim">No differences yet.</div>}
          </div>
        </div>
        <div className="flex flex-col gap-3 min-h-0 overflow-y-auto scroll-thin">
          <Panel title={`${ctl.label}${ctl.scenario ? " · " + ctl.scenario : ""}`} bodyClass="px-3.5 pb-3.5">
            <p className="text-[12px] text-muted mb-3">{ctl.desc}</p>
            <Btn tone="primary" size="lg" className="w-full" disabled={busy || (!!ctl.scenario && status[ctl.scenario]?.done) || (ctl.id === "delay" && !!results.delay)} onClick={trigger}>
              {busy ? "Running on the backend…" : ran && ctl.scenario && status[ctl.scenario]?.done ? "Already run — reset to repeat" : label}
            </Btn>
            <div className="mt-2"><ErrorNote error={err} /></div>
            <div className="mt-3">
              {key === "U-4.1" && results["U-4.1"] && <U41View r={results["U-4.1"]} approvals={items} />}
              {key === "U-4.2" && results["U-4.2"] && <U42View r={results["U-4.2"]} approvals={items} />}
              {key === "U-4.3" && (results["U-4.3-invalid"] || results["U-4.3-valid"]) && <U43View invalid={results["U-4.3-invalid"]} valid={results["U-4.3-valid"]} />}
              {key === "U-4.4" && results["U-4.4"] && <U44View r={results["U-4.4"]} />}
              {key === "U-4.5" && (results["U-4.5"] || status["U-4.5"]?.done) && (
                <U45View status={status["U-4.5"]} approvals={items} conflictBusy={conflict.isPending} lastExec={lastExec}
                  onConflict={() => { snap(); conflict.mutate({}, { onSuccess: (r: any) => { setResults((x) => ({ ...x, "U-4.5c": r })); setMissionId(r.mission_id); } }); }} />
              )}
              {key === "delay" && results.delay && (
                <div className="text-[12px]"><Chip status="DELAYED" /> {results.delay.flight} new departure <b className="mono">{results.delay.est}</b>, boarding closes {results.delay.boarding_close}. Passengers notified. Audited as a synthetic simulation event.</div>
              )}
              {key === "corridor" && corridor && (
                <div className="text-[12px]">
                  <div>Corridor <span className="mono">{corridor.edge_id}</span>: {corridor.available ? <Chip status="OK" label="REOPENED" size="xs" /> : <Chip status="BLOCKED" label="CLOSED" size="xs" />}</div>
                  {corridor.affected_routes.map((a: any, i: number) => (
                    <div key={i} className="mt-2 rounded-lg bg-white/[0.03] ring-1 ring-line p-2.5">
                      <div className="mono text-[11px]">{a.before.from} → {a.before.to} · {a.before.profile}</div>
                      <div className="text-red/90 text-[11.5px]">Before: {Math.round(a.before.distance_m)} m via {a.before.edge_path.includes("E_SKY_BC") ? "Skywalk B–C" : "…"}</div>
                      <div className={a.after?.ok ? "text-green/90 text-[11.5px]" : "text-red text-[11.5px]"}>
                        After: {a.after?.ok ? `${Math.round(a.after.distance_m)} m — ${a.after.steps.find((s: string) => /Follow|stair|corridor/i.test(s)) ?? "alternative path"}` : a.after?.reason ?? "no verified route — never fabricated"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>
          {mission.data && (
            <Panel title="Agent execution" bodyClass="px-3.5 pb-3.5"><MissionTimeline mission={mission.data} reveal /></Panel>
          )}
        </div>
      </div>
    </PageShell>
  );
}
