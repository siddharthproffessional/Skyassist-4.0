"use client";
import { useState } from "react";
import PageShell from "@/components/shell/PageShell";
import { AGENT_GLYPH } from "@/components/panels/AgentActivityPanel";
import MissionTimeline from "@/components/panels/MissionTimeline";
import { Btn, Chip, ErrorNote, Panel } from "@/components/ui/primitives";
import { useAction, useAgents, useMission, useMissions } from "@/lib/hooks";
import { statusTone } from "@/lib/colors";
import { localTime } from "@/lib/format";
import { get } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";

export default function AgentsPage() {
  const agents = useAgents();
  const missions = useMissions(30);
  const [pick, setPick] = useState<string | null>(null);
  const mid = pick ?? missions.data?.missions?.[0]?.mission_id ?? null;
  const mission = useMission(mid);
  const boundary = useAction("/web/agents/boundary-test");
  const alert = useAction("/web/alerts");
  const samples = useQuery({ queryKey: ["samples"], queryFn: () => get("/web/alerts/samples") });
  const [text, setText] = useState("");
  const [replay, setReplay] = useState(false);

  return (
    <PageShell title="Agent Mission Control"
      subtitle="Eight specialist agents with explicit tool allowlists over the deterministic SkyAssist services. Every status below is the agent's latest recorded step — nothing is animated to look busy."
      actions={<Btn tone="violet" disabled={boundary.isPending} onClick={() => boundary.mutate({}, { onSuccess: (r: any) => { setPick(r.mission_id); setReplay(true); } })}>
        Run permission boundary test
      </Btn>}>
      <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_1fr] gap-4">
        <div className="grid sm:grid-cols-2 gap-3 content-start">
          {agents.data?.agents.map((a) => {
            const tone = a.status === "IDLE" ? "slate" : statusTone(a.status);
            return (
              <article key={a.agent_id} className="glass rounded-xl p-3.5 flex flex-col gap-2">
                <header className="flex items-start gap-2.5">
                  <span className={`w-8 h-8 rounded-lg grid place-items-center text-[15px] ${a.status !== "IDLE" ? "bg-violet/15 text-violet" : "bg-white/5 text-dim"}`} aria-hidden>{AGENT_GLYPH[a.agent_id]}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[12px] font-semibold tracking-[0.08em]">{a.short}</div>
                    <div className="text-[10.5px] text-dim">{a.name} agent</div>
                  </div>
                  <Chip status={a.status} label={a.label} tone={tone as any} size="xs" />
                </header>
                <p className="text-[11.5px] text-muted leading-snug">{a.responsibility}</p>
                <div className="text-[11.5px] leading-snug rounded-lg bg-black/20 ring-1 ring-line px-2.5 py-1.5 min-h-[44px]">
                  {a.last_tool && <span className="mono text-[10.5px] text-violet mr-1">{a.last_tool}()</span>}{a.last}
                  {a.last_at && <div className="text-[10px] text-dim mono mt-0.5">{localTime(a.last_at, true)} · {a.steps} steps</div>}
                </div>
                <div>
                  <div className="label-xs mb-1">Authorised tools</div>
                  <div className="flex flex-wrap gap-1">
                    {a.tools.map((t) => (
                      <span key={t} title={agents.data?.tools[t]?.description} className="mono text-[10px] px-1.5 py-0.5 rounded bg-white/5 ring-1 ring-line text-muted">
                        {t}<span className="text-dim"> · {agents.data?.tools[t]?.kind}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="text-[10.5px] text-red/80">Never: {a.never.join("; ")}</div>
              </article>
            );
          })}
        </div>
        <div className="flex flex-col gap-4">
          <Panel title="Send an operational alert (Round 3 journey)" bodyClass="px-3.5 pb-3.5">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="e.g. OCC ALERT — SA-560 to BOM is CANCELLED (technical). Protect passengers on SA-562."
              className="w-full bg-black/30 ring-1 ring-line-2 rounded-lg px-3 py-2 text-[12.5px] outline-none focus:ring-cyan resize-none" />
            <div className="flex flex-wrap gap-1.5 my-2">
              {Object.entries(samples.data?.samples ?? {}).map(([k, v]) => (
                <button key={k} onClick={() => setText(v as string)} className="text-[10.5px] px-2 py-1 rounded-md ring-1 ring-line-2 text-muted hover:text-text">{k}</button>
              ))}
            </div>
            <Btn tone="primary" disabled={!text.trim() || alert.isPending}
              onClick={() => alert.mutate({ body: { text, source: "OCC" } }, { onSuccess: (r: any) => { setPick(r.mission_id); setReplay(true); } })}>
              {alert.isPending ? "Processing…" : "Submit alert"}
            </Btn>
            <div className="mt-2"><ErrorNote error={alert.error || boundary.error} /></div>
            <p className="text-[10.5px] text-dim mt-2">Checks → injection screen (before any AI) → AI intake (Gemini → Groq → rules) → Python validation → specialist agent → act or pause for a controller.</p>
          </Panel>
          <Panel title="Recorded execution" bodyClass="px-3.5 pb-3.5">
            {mission.data ? <MissionTimeline mission={mission.data} reveal={replay} /> : <div className="text-[12px] text-dim">No missions recorded in this dataset generation yet.</div>}
          </Panel>
          <Panel title="Mission history" bodyClass="pb-2">
            <ul>
              {missions.data?.missions.map((m) => (
                <li key={m.mission_id}>
                  <button onClick={() => { setPick(m.mission_id); setReplay(false); }}
                    className={`w-full text-left px-3.5 py-2 border-t hairline hover:bg-white/[0.03] ${m.mission_id === mid ? "bg-white/[0.04]" : ""}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] truncate">{m.title}</span><Chip status={m.status} size="xs" />
                    </div>
                    <div className="text-[10.5px] text-dim mono">{m.mission_id} · {m.kind} · {m.step_count} steps · {localTime(m.created_at, true)}</div>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </PageShell>
  );
}
