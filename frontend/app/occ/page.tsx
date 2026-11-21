"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import AuthGate from "@/components/shell/AuthGate";
import TopNav from "@/components/shell/TopNav";
import StatusBar from "@/components/shell/StatusBar";
import Intro from "@/components/shell/Intro";
import TwinView from "@/components/twin/TwinView";
import OperationalAlertPanel from "@/components/panels/OperationalAlertPanel";
import AgentActivityPanel from "@/components/panels/AgentActivityPanel";
import EntityPanel from "@/components/panels/EntityPanel";
import MissionTimeline from "@/components/panels/MissionTimeline";
import Situation from "@/components/panels/Situation";
import ApprovalCard from "@/components/panels/ApprovalCard";
import { Panel } from "@/components/ui/primitives";
import { useApprovals, useBagLegs, useLayout, useLiveUpdates, useMission, useMissions, useRoutes, useTwinState } from "@/lib/hooks";
import { useTwin } from "@/lib/store";

function OCC() {
  const live = useLiveUpdates();
  const st = useTwinState();
  const layout = useLayout();
  const sel = useTwin((s) => s.selection);
  const flightSel = sel?.kind === "flight" ? sel.id : null;
  const routes = useRoutes(flightSel);
  const legs = useBagLegs(flightSel);
  const missions = useMissions(5);
  const latest = missions.data?.missions?.[0];
  const mission = useMission(latest?.mission_id);
  const approvals = useApprovals();
  const [intro, setIntro] = useState<boolean | null>(null);
  const [tab, setTab] = useState<"ai" | "selected">("ai");
  useEffect(() => {
    let seen = false;
    try { seen = sessionStorage.getItem("sa_intro") === "1"; sessionStorage.setItem("sa_intro", "1"); } catch {}
    setIntro(!seen);
  }, []);
  useEffect(() => { if (sel) setTab("selected"); }, [sel]);
  const s = st.data;
  const firstPending = approvals.data?.items.find((i) => ["PENDING", "PENDING_APPROVAL", "ESCALATED"].includes(i.status) || i.can_execute);

  return (
    <div className="h-full flex flex-col">
      {intro && <Intro onDone={() => setIntro(false)} />}
      <TopNav pendingApprovals={s?.kpis.pending_approvals} />
      <main className="flex-1 relative min-h-0">
        <div className="absolute inset-0">
          {intro !== null && (
            <TwinView state={s} layout={layout.data} routes={routes.data?.routes} legs={legs.data?.legs} intro={!!intro} />
          )}
        </div>
        {/* left: operational picture */}
        <aside className="absolute left-3 top-3 bottom-3 w-[292px] flex flex-col gap-3 pointer-events-none z-10">
          {s && (
            <Panel title="Operational picture" className="pointer-events-auto shrink-0">
              <Situation s={s} mission={mission.data} />
            </Panel>
          )}
          {s && (
            <Panel title="Alerts" className="pointer-events-auto min-h-0 flex-1" bodyClass="overflow-y-auto scroll-thin h-full pb-2">
              <OperationalAlertPanel s={s} />
            </Panel>
          )}
        </aside>
        {/* right: AI operations / selected entity */}
        <aside className="absolute right-3 top-3 bottom-3 w-[344px] flex flex-col gap-3 pointer-events-none z-10">
          <div className="glass rounded-xl pointer-events-auto flex p-1 gap-1 shrink-0" role="tablist">
            {([["ai", "AI operations"], ["selected", sel ? `Selected · ${sel.id}` : "Selected entity"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                className={`flex-1 px-3 py-1.5 rounded-lg text-[12px] font-medium ${tab === k ? "bg-white/[0.07] text-text" : "text-muted hover:text-text"}`}>{l}</button>
            ))}
          </div>
          {tab === "selected" && (
            <Panel className="pointer-events-auto min-h-0 flex-1" bodyClass="overflow-y-auto scroll-thin h-full pt-3">
              {sel ? <EntityPanel /> : <div className="p-4 text-[12px] text-dim">Click a gate, stand or aircraft in the twin to inspect its live backend record.</div>}
            </Panel>
          )}
          {tab === "ai" && s && (
            <>
              <Panel title="Agent mission control" right={<Link href="/agents/" className="text-[11px] text-cyan hover:underline">Open →</Link>}
                className="pointer-events-auto shrink-0" bodyClass="max-h-[32vh] overflow-y-auto scroll-thin">
                <AgentActivityPanel agents={s.agents} dense={false} />
              </Panel>
              <Panel title="Latest recorded execution" className="pointer-events-auto min-h-0 flex-1" bodyClass="overflow-y-auto scroll-thin h-full px-3.5 pb-3">
                {mission.data ? <MissionTimeline mission={mission.data} compact /> :
                  <div className="text-[12px] text-dim">No agent mission yet. Run a scenario in <Link className="text-cyan" href="/recovery/">Recovery</Link> or the guided <Link className="text-cyan" href="/demo/">Demo</Link>.</div>}
              </Panel>
              {firstPending && (
                <div className="pointer-events-auto shrink-0 max-h-[34vh] overflow-y-auto scroll-thin rounded-xl">
                  <ApprovalCard item={firstPending} compact />
                </div>
              )}
            </>
          )}
        </aside>
      </main>
      <StatusBar s={s} live={live} />
    </div>
  );
}

export default function Page() {
  return <AuthGate role="COORDINATOR"><OCC /></AuthGate>;
}
