"use client";
import { useMemo } from "react";
import type { BagLeg, Layout, RouteR, TwinState } from "@/lib/types";
import { GATE_COLOR, HEALTH_COLOR } from "@/lib/colors";
import { useTwin } from "@/lib/store";

/** 2D fallback: the routing graph drawn with its own (illustrative) x/y coordinates. Same backend state as 3D. */
export default function Twin2D({ state, layout, routes = [], legs = [], compact = false, onSelectGate }: {
  state?: TwinState; layout: Layout; routes?: RouteR[]; legs?: BagLeg[]; compact?: boolean;
  onSelectGate?: (gate: string) => void;
}) {
  const sel = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  const focus = useTwin((s) => s.focusRoute);
  const layers = useTwin((s) => s.layers);
  const nodes = useMemo(() => new Map(layout.nodes.map((n) => [n.node_id, n])), [layout]);
  const gates = useMemo(() => new Map((state?.gates ?? []).map((g) => [g.gate, g])), [state]);
  const flightsByGate = useMemo(() => {
    const m = new Map<string, any[]>();
    state?.flights.forEach((f) => f.gate && m.set(f.gate, [...(m.get(f.gate) ?? []), f]));
    return m;
  }, [state]);
  const closed = new Set(state?.closed_edges.map((e) => e.edge_id) ?? []);
  const P = (id: string) => {
    const n = nodes.get(id);
    return n ? [n.x, n.y] : [0, 0];
  };
  const poly = (path?: string[]) => (path ?? []).map((id) => P(id).join(",")).join(" ");
  const gatePos = (g: string) => P(`G_${g}`);
  const flightCount = state?.flights.length ?? 0;

  return (
    <svg viewBox="40 60 880 600" className="w-full h-full select-none" role="img"
      aria-label="2D terminal map (illustrative geometry from the SkyAssist routing graph)">
      <defs>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(148,170,200,0.05)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect x="40" y="60" width="880" height="600" fill="url(#grid)" />
      {/* corridors */}
      {layout.edges.map((e) => {
        const pts = e.geometry ? e.geometry.map((p) => p.join(",")).join(" ") : `${P(e.from_node).join(",")} ${P(e.to_node).join(",")}`;
        const isClosed = closed.has(e.edge_id) || !e.available;
        const w = e.kind === "CONNECTOR" ? 5 : e.kind === "CONCOURSE" ? 7 : 2.5;
        return (
          <polyline key={e.edge_id} points={pts} fill="none" strokeLinecap="round"
            stroke={isClosed ? "#f25f5c" : e.kind === "STAIRS" ? "#5f6e84" : "#1d2a3e"} strokeWidth={isClosed ? w + 1 : w}
            strokeDasharray={isClosed ? "6 5" : e.kind === "STAIRS" ? "3 4" : undefined} />
        );
      })}
      {/* routes */}
      {layers.routes && routes.filter((r) => r.ok).map((r, i) => (
        <polyline key={i} points={poly(r.node_path)} fill="none" stroke={r.profile === "STANDARD" ? "#3ec5ff" : "#7ee0ff"}
          strokeWidth={2} opacity={focus ? 0.25 : 0.65} strokeLinejoin="round" />
      ))}
      {focus && <polyline points={poly(focus)} fill="none" stroke="#ffffff" strokeWidth={3.5} strokeLinejoin="round" />}
      {/* baggage legs (gate → sortation → gate) */}
      {layers.baggage && legs.map((l, i) => {
        if (!l.from_gate || !l.to_gate) return null;
        const a = gatePos(l.from_gate), b = gatePos(l.to_gate);
        const mid = [480, 640];
        return (
          <polyline key={i} points={`${a.join(",")} ${a[0]},${mid[1] - 20} ${b[0]},${mid[1] - 20} ${b.join(",")}`} fill="none"
            stroke={l.discrepancy ? "#f5b544" : "#8aa4c2"} strokeWidth={l.discrepancy ? 2.4 : 1.2} strokeDasharray="4 4" opacity={0.85} />
        );
      })}
      {/* hubs & landmarks */}
      {layout.nodes.filter((n) => n.node_type !== "GATE").map((n) => (
        <g key={n.node_id}>
          <circle cx={n.x} cy={n.y} r={n.node_type === "HUB" ? 7 : 4}
            fill={n.node_type === "HUB" ? "#0d1524" : n.node_type === "CHECKPOINT" ? "#f5b544" : n.node_type === "CONNECTOR" ? "#3ec5ff" : "#a78bfa"}
            stroke="#3ec5ff" strokeWidth={n.node_type === "HUB" ? 1.5 : 0} />
          {!compact && n.node_type === "HUB" && (
            <text x={n.x} y={n.y + 22} textAnchor="middle" fontSize="11" fill="#93a1b5" fontWeight={600} letterSpacing="1.5">
              CONCOURSE {n.concourse}
            </text>
          )}
        </g>
      ))}
      {/* gates */}
      {layout.gates.map(({ gate }) => {
        const g = gates.get(gate);
        const [x, y] = gatePos(gate);
        const color = g ? (g.cancelled.length && g.status === "AVAILABLE" ? "#f25f5c" : GATE_COLOR[g.status]) : "#2a3a52";
        const fl = flightsByGate.get(gate) ?? [];
        const selected = sel?.kind === "gate" && sel.id === gate;
        const fWorst = fl.find((f) => f.health === "critical") ?? fl.find((f) => f.health === "warning") ?? fl[0];
        const left = Number(gate.slice(1)) % 2 === 1;
        return (
          <g key={gate} className="cursor-pointer" onClick={() => { select({ kind: "gate", id: gate }); onSelectGate?.(gate); }}
            role="button" aria-label={`Gate ${gate}: ${g?.status ?? "unknown"}`}>
            <circle cx={x} cy={y} r={selected ? 7.5 : 5.5} fill={color} stroke={selected ? "#fff" : "#060a12"} strokeWidth={1.5} />
            {!compact && (
              <text x={left ? x - 12 : x + 12} y={y + 3.5} textAnchor={left ? "end" : "start"} fontSize="9.5" fill="#c9d6e6"
                className="mono">{gate}{fWorst && flightCount ? ` · ${fWorst.flight_no}` : ""}</text>
            )}
            {fWorst && (
              <rect x={left ? x - 9 : x + 6} y={y - 8} width="3" height="3" fill={HEALTH_COLOR[fWorst.health as "normal"]} />
            )}
          </g>
        );
      })}
      <text x="56" y="652" fontSize="10" fill="#5f6e84">Illustrative layout · walking distances come from graph edge lengths · synthetic data</text>
    </svg>
  );
}
