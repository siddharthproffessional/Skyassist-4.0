"use client";
import { useQuery } from "@tanstack/react-query";
import PageShell from "@/components/shell/PageShell";
import { Btn, Chip, ErrorNote, KV, Metric, Panel } from "@/components/ui/primitives";
import { get } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { localTime } from "@/lib/format";

export default function MonitoringPage() {
  const q = useQuery({ queryKey: ["monitoring"], queryFn: () => get("/web/monitoring"), refetchInterval: 10_000 });
  const sim = useAction("/web/monitoring/simulate");
  const br = useAction("/web/monitoring/reset-breakers");
  const burst = useAction("/web/monitoring/burst");
  const d = q.data;
  const providers = d?.health?.providers ?? [];
  const byProv = (p: string) => (d?.llm_calls ?? []).filter((c: any) => c.provider === p);
  return (
    <PageShell title="Reliability & Observability"
      subtitle="Round 3 resilience, unchanged: Gemini 2.5 Flash → Groq Llama 3.3 70B → deterministic rules. A provider is shown healthy only after a successful call; with no keys configured SkyAssist runs rules-only."
      actions={<Btn tone="violet" disabled={burst.isPending} onClick={() => burst.mutate({})}>{burst.isPending ? "Running burst…" : "Run 12-alert burst (4 workers)"}</Btn>}>
      <ErrorNote error={sim.error || br.error || burst.error} />
      <div className="grid md:grid-cols-3 gap-3 mb-4">
        {[...providers, { provider: "rules", status: "ALWAYS_AVAILABLE", last_outcome: "deterministic fallback" }].map((p: any, i: number) => (
          <Panel key={p.provider} title={`${i + 1} · ${p.provider === "rules" ? "Rules fallback" : p.provider === "gemini" ? "Gemini 2.5 Flash" : "Groq Llama 3.3 70B"}`} bodyClass="px-3.5 pb-3.5">
            <Chip status={p.status === "NOT_CONFIGURED" ? "NOT CONFIGURED" : p.status} tone={p.status === "NOT_CONFIGURED" ? "slate" : undefined} />
            <div className="mt-2">
              <KV k="Last outcome" v={p.last_outcome ?? "—"} />
              {p.provider !== "rules" && <>
                <KV k="Calls" v={byProv(p.provider).reduce((a: number, c: any) => a + c.n, 0)} mono />
                <KV k="Circuit" v={d?.breakers?.[p.provider]?.open ? `OPEN (${d.breakers[p.provider].reopens_in_s}s)` : "closed"} mono />
                <KV k="Simulated" v={[d?.simulation?.outage?.includes(p.provider) && "outage", d?.simulation?.slow?.includes(p.provider) && "slow"].filter(Boolean).join(", ") || "—"} />
              </>}
            </div>
            {p.provider !== "rules" && (
              <div className="flex gap-1.5 mt-2.5">
                <Btn size="sm" onClick={() => sim.mutate({ body: { provider: p.provider, outage: !d?.simulation?.outage?.includes(p.provider) } })}>
                  {d?.simulation?.outage?.includes(p.provider) ? "End simulated outage" : "Simulate outage"}
                </Btn>
                <Btn size="sm" tone="ghost" onClick={() => br.mutate({})}>Reset breaker</Btn>
              </div>
            )}
          </Panel>
        ))}
      </div>
      <div className="glass rounded-xl px-4 py-3 grid grid-cols-3 md:grid-cols-6 xl:grid-cols-9 gap-4 mb-4">
        <Metric label="Alerts processed" value={d?.alerts_processed ?? "—"} />
        <Metric label="Latency p50" value={d?.latency_p50_ms != null ? `${Math.round(d.latency_p50_ms)} ms` : "—"} />
        <Metric label="Latency p95" value={d?.latency_p95_ms != null ? `${Math.round(d.latency_p95_ms)} ms` : "—"} />
        <Metric label="Retries" value={d?.retries ?? "—"} />
        <Metric label="Duplicates" value={d?.duplicates ?? "—"} />
        <Metric label="Attacks blocked" value={d?.blocked_attacks ?? "—"} tone="green" />
        <Metric label="Failed workflows" value={d?.failed_workflows ?? "—"} tone={d?.failed_workflows ? "amber" : undefined} />
        <Metric label="Escalations" value={d?.escalations ?? "—"} />
        <Metric label="Est. AI cost" value={d ? `$${d.estimated_cost_usd.toFixed(4)}` : "—"} sub="from logged tokens" />
      </div>
      <div className="grid xl:grid-cols-[1fr_1.4fr] gap-3">
        <Panel title="Configured values (from the repository)" bodyClass="px-3.5 pb-3.5">
          {d && Object.entries(d.config).map(([k, v]) => <KV key={k} k={k.replace(/_/g, " ")} v={String(v)} mono />)}
          <div className="mt-3 label-xs">Workflow orchestration</div>
          <KV k="n8n outbox mode" v={d?.outbox?.mode} mono />
          <KV k="Outbox" v={JSON.stringify(d?.outbox?.stats ?? {})} mono />
          <KV k="n8n workflows" v={(d?.n8n_workflows ?? []).join(", ")} />
          <div className="text-[10.5px] text-dim mt-2">{d?.pricing_note}</div>
        </Panel>
        <Panel title="Recent alert runs — which provider actually answered" bodyClass="pb-2 overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead><tr className="text-left border-b hairline">{["Time", "Run", "Source", "Type", "Provider", "Status", "ms"].map((h) => <th key={h} className="px-3 py-1.5 label-xs font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {(d?.recent_runs ?? []).map((r: any) => (
                <tr key={r.run_id} className="border-b hairline last:border-0">
                  <td className="px-3 py-1.5 mono text-dim">{localTime(r.created_at, true)}</td>
                  <td className="px-3 py-1.5 mono">{r.run_id}</td>
                  <td className="px-3 py-1.5 text-muted">{r.source}</td>
                  <td className="px-3 py-1.5 text-muted">{r.alert_type ?? "—"}</td>
                  <td className="px-3 py-1.5 mono">{r.ai_provider ?? (r.safety_case === "ATTACK_BLOCKED" ? "not called (blocked)" : "—")}</td>
                  <td className="px-3 py-1.5"><Chip status={r.status} size="xs" /></td>
                  <td className="px-3 py-1.5 mono text-dim">{r.latency_ms ? Math.round(r.latency_ms) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!d?.recent_runs?.length && <div className="px-3.5 py-3 text-[12px] text-dim">No alerts processed yet. Use “Run 12-alert burst” or submit an alert on the Agents page.</div>}
        </Panel>
      </div>
      {burst.data && (
        <Panel title={`Burst ${burst.data.batch_id} · ${burst.data.wall_ms} ms wall · ${burst.data.workers} workers · ${burst.data.ai_calls} AI calls`} className="mt-3" bodyClass="pb-2 overflow-x-auto">
          <table className="w-full text-[12px]">
            <tbody>
              {burst.data.results.map((r: any) => (
                <tr key={r["#"]} className="border-b hairline last:border-0">
                  <td className="px-3 py-1.5 mono text-dim">{r["#"]}</td><td className="px-3 py-1.5">{r.alert}</td>
                  <td className="px-3 py-1.5"><Chip status={r.status} size="xs" /></td><td className="px-3 py-1.5 text-muted">{r["safety case"]}</td>
                  <td className="px-3 py-1.5 mono">{r.AI}</td><td className="px-3 py-1.5 mono text-dim">{r.ms ? Math.round(r.ms) : "—"} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </PageShell>
  );
}
