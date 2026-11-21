"use client";
import { create } from "zustand";

export type Selection = { kind: "gate"; id: string } | { kind: "flight"; id: string } | null;
export type CameraPreset = "full" | "A" | "B" | "C" | "departures" | "routes" | "ground";

export interface Layers {
  roof: boolean;
  labels: boolean;
  aircraft: boolean;
  routes: boolean;
  baggage: boolean;
  skywalk: boolean;
  heatmap: boolean;
}

interface TwinStore {
  selection: Selection;
  select: (s: Selection) => void;
  preset: CameraPreset;
  presetNonce: number;
  setPreset: (p: CameraPreset) => void;
  layers: Layers;
  toggle: (k: keyof Layers) => void;
  setLayers: (l: Partial<Layers>) => void;
  mode: "3d" | "2d";
  setMode: (m: "3d" | "2d") => void;
  simulate: boolean; // synthetic movement dots (only when a simulation is active)
  setSimulate: (b: boolean) => void;
  focusRoute: string[] | null; // node path highlighted on top of the layers
  setFocusRoute: (p: string[] | null) => void;
}

export const useTwin = create<TwinStore>((set) => ({
  selection: null,
  select: (selection) => set({ selection }),
  preset: "full",
  presetNonce: 0,
  setPreset: (preset) => set((s) => ({ preset, presetNonce: s.presetNonce + 1 })),
  layers: { roof: true, labels: true, aircraft: true, routes: true, baggage: true, skywalk: true, heatmap: false },
  toggle: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  setLayers: (l) => set((s) => ({ layers: { ...s.layers, ...l } })),
  mode: "3d",
  setMode: (mode) => set({ mode }),
  simulate: false,
  setSimulate: (simulate) => set({ simulate }),
  focusRoute: null,
  setFocusRoute: (focusRoute) => set({ focusRoute }),
}));

// QA hook: lets the browser test select twin entities without pixel-picking. Read-only view of client UI state.
if (typeof window !== "undefined") (window as any).__skyTwin = useTwin;
