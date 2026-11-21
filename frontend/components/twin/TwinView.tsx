"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { BagLeg, Layout, RouteR, TwinState } from "@/lib/types";
import { useTwin, type CameraPreset, type Layers } from "@/lib/store";
import { GATE_COLOR, GATE_LABEL } from "@/lib/colors";
import Twin2D from "./Twin2D";

const AirportScene = dynamic(() => import("./AirportScene"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-dim text-sm">Building the digital twin…</div>,
});

function webglOK() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

const PRESET_LABELS: [CameraPreset, string][] = [
  ["full", "Full airport"], ["A", "Concourse A"], ["B", "Concourse B"], ["C", "Concourse C"],
  ["departures", "Departure gates"], ["routes", "Passenger routes"], ["ground", "Ground ops"],
];
const LAYER_LABELS: [keyof Layers, string][] = [
  ["roof", "Roofs"], ["labels", "Labels"], ["aircraft", "Aircraft"], ["routes", "Pax routes"], ["baggage", "Baggage"],
  ["skywalk", "Level 2"], ["heatmap", "Heatmap"],
];

export default function TwinView({ state, layout, routes, legs, intro, compact, toolbar = true, highlightGates, className = "" }: {
  state?: TwinState; layout?: Layout; routes?: RouteR[]; legs?: BagLeg[]; intro?: boolean; compact?: boolean;
  toolbar?: boolean; highlightGates?: string[]; className?: string;
}) {
  const mode = useTwin((s) => s.mode);
  const setMode = useTwin((s) => s.setMode);
  const setPreset = useTwin((s) => s.setPreset);
  const layers = useTwin((s) => s.layers);
  const toggle = useTwin((s) => s.toggle);
  const simulate = useTwin((s) => s.simulate);
  const setSimulate = useTwin((s) => s.setSimulate);
  const [gl, setGl] = useState<boolean | null>(null);
  const [open, setOpen] = useState<"views" | "layers" | null>(null);
  useEffect(() => {
    const ok = webglOK();
    setGl(ok);
    const force2d = new URLSearchParams(window.location.search).get("mode") === "2d";
    if (!ok || force2d) setMode("2d");
  }, [setMode]);

  const ready = state && layout;
  const use3d = mode === "3d" && gl;
  return (
    <div className={`relative w-full h-full overflow-hidden ${className}`}>
      {!ready && <div className="absolute inset-0 grid place-items-center text-dim text-sm">Loading airport state…</div>}
      {ready && use3d && (
        <AirportScene state={state} layout={layout} routes={routes} legs={legs} intro={intro} compact={compact}
          highlightGates={highlightGates} />
      )}
      {ready && !use3d && gl !== null && (
        <div className="absolute inset-0 p-4"><Twin2D state={state} layout={layout} routes={routes} legs={legs} compact={compact} /></div>
      )}

      {toolbar && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1 glass rounded-xl p-1 z-10">
          <div className="relative">
            <button className="px-2.5 py-1 rounded-lg text-[11.5px] text-muted hover:text-text hover:bg-white/5" onClick={() => setOpen(open === "views" ? null : "views")}
              aria-expanded={open === "views"} disabled={!use3d}>Views ▾</button>
            {open === "views" && use3d && (
              <div className="absolute top-9 left-0 glass rounded-lg p-1 w-44 flex flex-col">
                {PRESET_LABELS.map(([k, l]) => (
                  <button key={k} className="text-left px-2.5 py-1.5 rounded-md text-[12px] hover:bg-white/5" onClick={() => { setPreset(k); setOpen(null); }}>{l}</button>
                ))}
              </div>
            )}
          </div>
          <div className="relative">
            <button className="px-2.5 py-1 rounded-lg text-[11.5px] text-muted hover:text-text hover:bg-white/5" onClick={() => setOpen(open === "layers" ? null : "layers")}
              aria-expanded={open === "layers"}>Layers ▾</button>
            {open === "layers" && (
              <div className="absolute top-9 left-0 glass rounded-lg p-1.5 w-44 flex flex-col">
                {LAYER_LABELS.map(([k, l]) => (
                  <label key={k} className="flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] hover:bg-white/5 cursor-pointer">
                    <input type="checkbox" checked={layers[k]} onChange={() => toggle(k)} className="accent-cyan-400" />{l}
                  </label>
                ))}
              </div>
            )}
          </div>
          <span className="w-px h-4 bg-line-2 mx-0.5" />
          <button className="px-2.5 py-1 rounded-lg text-[11.5px] text-muted hover:text-text hover:bg-white/5" disabled={!use3d}
            onClick={() => setPreset("full")} title="Reset camera">Reset</button>
          <button className={`px-2.5 py-1 rounded-lg text-[11.5px] ${simulate ? "text-violet bg-violet/15" : "text-muted hover:text-text hover:bg-white/5"}`}
            onClick={() => setSimulate(!simulate)} title="Animated dots show SYNTHETIC simulated movement only">
            {simulate ? "◉ Simulation" : "○ Simulation"}
          </button>
          <span className="w-px h-4 bg-line-2 mx-0.5" />
          <div className="flex rounded-lg ring-1 ring-line-2 overflow-hidden" role="group" aria-label="Render mode">
            {(["3d", "2d"] as const).map((m) => (
              <button key={m} disabled={m === "3d" && !gl}
                className={`px-2.5 py-1 text-[11px] font-semibold mono ${mode === m ? "bg-cyan/15 text-cyan" : "text-muted hover:text-text"}`}
                onClick={() => setMode(m)}>{m.toUpperCase()}</button>
            ))}
          </div>
        </div>
      )}

      {toolbar && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 glass rounded-lg px-3 py-1.5 flex items-center gap-3 z-10 text-[10.5px] text-muted whitespace-nowrap">
          {(["OCCUPIED", "BOARDING", "PENDING_APPROVAL", "BLOCKED", "AVAILABLE"] as const).map((s) => (
            <span key={s} className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: GATE_COLOR[s] }} />{GATE_LABEL[s]}
            </span>
          ))}
          <span className="flex items-center gap-1.5"><span className="w-4 h-[3px] rounded bg-cyan" />Pax route</span>
          <span className="flex items-center gap-1.5"><span className="w-4 h-[3px] rounded bg-amber" />Bags separated</span>
          <span className="text-dim">· illustrative geometry</span>
        </div>
      )}
      {simulate && toolbar && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 text-[10.5px] text-violet bg-violet/10 ring-1 ring-violet/30 rounded-md px-2 py-0.5 z-10">
          Simulation active — moving dots are synthetic, not live tracking
        </div>
      )}
    </div>
  );
}
