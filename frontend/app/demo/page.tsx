"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import AuthGate from "@/components/shell/AuthGate";
import TopNav from "@/components/shell/TopNav";
import StatusBar from "@/components/shell/StatusBar";
import TwinView from "@/components/twin/TwinView";
import MissionTimeline from "@/components/panels/MissionTimeline";
import ApprovalCard from "@/components/panels/ApprovalCard";
import { Btn, Chip, ErrorNote, SyntheticBadge } from "@/components/ui/primitives";
import { get } from "@/lib/api";
import { useAction, useApprovals, useBagLegs, useLayout, useLiveUpdates, useMission, useRoutes, useTwinState } from "@/lib/hooks";
import { useTwin } from "@/lib/store";
import { localTime } from "@/lib/format";

const ALERT_560 = "OCC ALERT 09:40 — SA-560 to BOM is CANCELLED (technical). 40 passengers. Protect them on SA-562.";
const ALERT_591 = "SA-591 cancelled, crew sickness. Please rebook the Rahman family (PNRBAG).";
const STAGES = ["Prepare", "Identify", "Investigate", "Recover", "Human decision", "Result"];

function Demo() {
  const live = useLiveUpdates();
  const st = useTwinState();
  const layout = useLayout();
  const approvals = useApprovals();
  const [stage, setStage] = useState(0);
  const [missionId, setMissionId] = useState<string | null>(null);
  const [recover, setRecover] = useState<{ a?: any; b?: any }>({});
  const [before, setBefore] = useState<any>(null);
  const mission = useMission(missionId);
  const routes = useRoutes(stage >= 5 ? "SA-592" : null);
  const legs = useBagLegs(null);
  const setPreset = useTwin((s) => s.setPreset);
  const setSimulate = useTwin((s) => s.setSimulate);
  const setLayers = useTwin((s) => s.setLayers);
  const select = useTwin((s) => s.select);
  const reset = useAction("/web/scenarios/reset");
  const inv = useAction("/web/demo/investigate");
  const alert = useAction("/web/alerts");
  const f560 = useQuery({ queryKey: ["flight", "SA-560"], queryFn: () => get("/web/flights/SA-560"), enabled: stage >= 1 });
  const audit = useQuery({ queryKey: ["audit-demo", stage], queryFn: () => get("/web/audit?limit=40&passenger=PNRBAG"), enabled: stage >= 5 });
  const err = reset.error || inv.error || alert.error;
  const pendingJ = approvals.data?.items.find((i) => i.kind === "journey" && i.status === "PENDING");
  const decidedJ = approvals.data?.items.find((i) => i.kind === "journey" && i.status !== "PENDING");

  useEffect(() => { setLayers({ heatmap: stage === 1, routes: true, baggage: true }); }, [stage, setLayers]);
  useEffect(() => { if (decidedJ && stage === 4) { setStage(5); setPreset("B"); setSimulate(true); select({ kind: "flight", id: "SA-592" }); } }, [decidedJ, stage, setPreset, setSimulate, select]);

  const kp = st.data?.kpis;
  const go = {
    prepare: () => reset.mutate({}, { onSuccess: () => { setStage(1); setPreset("full"); setMissionId(null); setRecover({}); setSimulate(false); } }),
    investigate: () => inv.mutate({}, { onSuccess: (r: any) => { setMissionId(r.mission_id); setStage(2); setPreset("C"); } }),
    recover: () => {
      setBefore(kp ? { ...kp } : null);
      alert.mutate({ body: { text: ALERT_560, source: "OCC" } }, {
        onSuccess: (a: any) => {
          setRecover((x) => ({ ...x, a }));
          alert.mutate({ body: { text: ALERT_591, source: "OCC" } }, {
            onSuccess: (b: any) => { setRecover((x) => ({ ...x, b })); setMissionId(b.mission_id); setStage(3); setPreset("B"); setSimulate(true); },
          });
        },
      });
    },
  };

  return (
    <div className="h-full flex flex-col">
      <TopNav pendingApprovals={kp?.pending_approvals} />
      <main className="flex-1 relative min-h-0">
        <div className="absolute inset-0">
          <TwinView state={st.data} layout={layout.data} routes={routes.data?.routes} legs={legs.data?.legs} />
        </div>
        <div className="absolute top-3 left-3 right-3 z-20 flex justify-center pointer-events-none">
          <ol className="glass rounded-xl px-2 py-1.5 flex items-center gap-1 pointer-events-auto mt-11">
            {STAGES.map((s, i) => (
              <li key={s} className={`px-3 py-1 rounded-lg text-[11.5px] font-medium flex items-center gap-1.5 ${i === stage ? "bg-cyan/15 text-cyan" : i < stage ? "text-green" : "text-dim"}`}>
                <span className="mono">{i < stage ? "✓" : i}</span>{s}
              </li>
            ))}
          </ol>
        </div>
        <aside className="absolute left-3 top-3 bottom-3 w-[400px] z-10 flex flex-col gap-3 pointer-events-none">
          <section className="glass rounded-xl p-4 pointer-events-auto overflow-y-auto scroll-thin min-h-0 flex-1">
            <div className="flex items-center justify-between mb-2"><span className="label-xs">Guided demonstration</span><SyntheticBadge text="Seeded synthetic scenario" /></div>
            {stage === 0 && (
              <>
                <h2 className="text-[18px] font-semibold leading-snug">A morning disruption at the hub</h2>
                <p className="text-[12.5px] text-muted mt-2">This demo is deterministic and repeatable: it restores the seeded synthetic dataset, then every step calls the real backend. Nothing is faked — the approval in step 4 is yours to make.</p>
                <Btn tone="primary" size="lg" className="w-full mt-4" disabled={reset.isPending} onClick={go.prepare}>{reset.isPending ? "Restoring…" : "Start — restore the synthetic airport"}</Btn>
              </>
            )}
            {stage === 1 && (
              <>
                <h2 className="text-[18px] font-semibold">1 · Identify</h2>
                <p className="text-[12.5px] text-muted mt-1">Two departures are cancelled. The red stands and the heatmap show where passengers are affected.</p>
                <div className="grid grid-cols-3 gap-2 mt-3">
                  <div className="rounded-lg bg-red/10 ring-1 ring-red/30 p-2.5"><div className="label-xs">Disrupted</div><div className="mono text-[22px] text-red">{kp?.disrupted_flights}</div></div>
                  <div className="rounded-lg bg-amber/10 ring-1 ring-amber/30 p-2.5"><div className="label-xs">Affected pax</div><div className="mono text-[22px] text-amber">{kp?.affected_passengers}</div></div>
                  <div className="rounded-lg bg-white/5 ring-1 ring-line p-2.5"><div className="label-xs">Vulnerable</div><div className="mono text-[22px]">{f560.data?.vulnerable_count ?? "…"}</div></div>
                </div>
                <div className="mt-3 text-[12px]">
                  <div><Chip status="CANCELLED" /> <span className="mono">SA-560</span> → BOM · Gate C05 · {f560.data?.passenger_count ?? "…"} bookings</div>
                  <div className="mt-1"><Chip status="CANCELLED" /> <span className="mono">SA-591</span> → LHR · Gate B12 · Rahman family, 2 bags</div>
                  <p className="text-dim text-[11px] mt-2">Vulnerable = recorded booking needs only (wheelchair, unaccompanied minor, elderly) — never inferred.</p>
                </div>
                <Btn tone="violet" size="lg" className="w-full mt-4" disabled={inv.isPending} onClick={go.investigate}>Next — agents investigate (read-only)</Btn>
              </>
            )}
            {stage === 2 && (
              <>
                <h2 className="text-[18px] font-semibold">2 · Investigate</h2>
                <p className="text-[12.5px] text-muted mt-1">Specialist agents call read-only tools: affected passengers, baggage feasibility, crew, maintenance and gate state. No record was changed.</p>
                <div className="mt-3">{mission.data && <MissionTimeline mission={mission.data} reveal compact />}</div>
                <Btn tone="primary" size="lg" className="w-full mt-3" disabled={alert.isPending} onClick={go.recover}>{alert.isPending ? "Agents recovering…" : "Next — recover"}</Btn>
              </>
            )}
            {stage === 3 && (
              <>
                <h2 className="text-[18px] font-semibold">3 · Recover</h2>
                <div className="grid grid-cols-2 gap-2 mt-2 text-[12px]">
                  <div className="rounded-lg bg-white/[0.03] ring-1 ring-line p-2.5"><div className="label-xs">Before</div>Affected {before?.affected_passengers} · rebooked {before?.rebooked_passengers}</div>
                  <div className="rounded-lg bg-green/10 ring-1 ring-green/30 p-2.5"><div className="label-xs">After</div>Affected {kp?.affected_passengers} · rebooked {kp?.rebooked_passengers}</div>
                </div>
                <div className="mt-3 text-[12px]">
                  <div><Chip status={recover.a?.run?.status} /> SA-560: safe action committed automatically (vulnerable first, batches of 10).</div>
                  <div className="mt-1"><Chip status={recover.b?.run?.status} /> SA-591: bags cannot make a 35-min connection (45-min minimum) — paused for a controller.</div>
                </div>
                <div className="mt-3">{mission.data && <MissionTimeline mission={mission.data} reveal compact />}</div>
                <Btn tone="primary" size="lg" className="w-full mt-3" onClick={() => setStage(4)}>Next — human decision</Btn>
              </>
            )}
            {stage === 4 && (
              <>
                <h2 className="text-[18px] font-semibold">4 · Human decision</h2>
                <p className="text-[12.5px] text-muted mt-1">The AI recommends; a controller decides. Approving commits seat + bags + delivery note in one transaction, re-validated at execution. Declining changes nothing.</p>
                <div className="mt-3">{pendingJ ? <ApprovalCard item={pendingJ} compact /> : <div className="text-[12px] text-dim">Waiting for the approval to load…</div>}</div>
              </>
            )}
            {stage === 5 && (
              <>
                <h2 className="text-[18px] font-semibold">5 · Result</h2>
                <p className="text-[12.5px] text-muted mt-1">
                  {decidedJ?.status === "APPROVED_EXECUTED" ? <>The Rahman family is on <b className="mono">SA-592</b>; their bags travel on <b className="mono">SA-594</b> — the amber baggage line in the twin. Passengers were notified on their phones.</> : <>Decision recorded: <Chip status={decidedJ?.status} size="xs" />. Nothing was executed.</>}
                </p>
                <div className="label-xs mt-3 mb-1">Audit trail · PNRBAG</div>
                <ul className="text-[11.5px]">
                  {(audit.data?.events ?? []).slice(0, 12).map((e: any) => (
                    <li key={e.event_id} className="flex gap-2 py-0.5 border-t hairline">
                      <span className="mono text-dim">{localTime(e.occurred_at, true)}</span><span className="mono">{e.event_type}</span>{e.result && <Chip status={e.result} size="xs" />}
                    </li>
                  ))}
                </ul>
                <div className="flex gap-2 mt-3">
                  <a href="/audit/?passenger=PNRBAG" className="flex-1"><Btn className="w-full">Full audit</Btn></a>
                  <Btn tone="ghost" onClick={() => setStage(0)}>Restart demo</Btn>
                </div>
              </>
            )}
            <div className="mt-3"><ErrorNote error={err} /></div>
          </section>
        </aside>
      </main>
      <StatusBar s={st.data} live={live} />
    </div>
  );
}

export default function Page() {
  return <AuthGate role="COORDINATOR"><Demo /></AuthGate>;
}
