"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useThree } from "@react-three/fiber";
import { CameraControls, Environment, Lightformer, PerformanceMonitor } from "@react-three/drei";
import { Bloom, EffectComposer, N8AO, Vignette } from "@react-three/postprocessing";
import type { BagLeg, Flight, Layout, RouteR, TwinState } from "@/lib/types";
import { useTwin } from "@/lib/store";
import { BaggageHall, Concourse, Ground, LightMasts, MainTerminal, Skywalk } from "./TerminalModel";
import GateObject from "./GateObject";
import FlightObject from "./FlightObject";
import { BaggageRouteLayer, Heatmap, PassengerRouteLayer } from "./RouteLayers";
import { PRESETS, standPos } from "./layout3d";
import ApprovedGLB from "./ApprovedGLB";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";

export interface SceneProps {
  state: TwinState;
  layout: Layout;
  routes?: RouteR[];
  legs?: BagLeg[];
  intro?: boolean;
  compact?: boolean;          // secondary view (e.g. BEFORE snapshot): lighter rendering
  interactive?: boolean;
  highlightGates?: string[];  // dim everything else
}

function CameraRig({ intro, compact }: { intro?: boolean; compact?: boolean }) {
  const ref = useRef<CameraControls>(null);
  const preset = useTwin((s) => s.preset);
  const nonce = useTwin((s) => s.presetNonce);
  const sel = useTwin((s) => s.selection);
  const state = useRef<{ flights: Flight[] }>({ flights: [] });
  const { scene } = useThree();
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const p = PRESETS.full;
    if (intro) {
      c.setLookAt(130, 120, 150, 0, 0, -10, false);
      const t = setTimeout(() => c.setLookAt(...p.pos, ...p.target, true), 350);
      return () => clearTimeout(t);
    }
    c.setLookAt(...p.pos, ...p.target, false);
  }, [intro]);
  useEffect(() => {
    if (!ref.current || nonce === 0) return;
    const p = PRESETS[preset];
    ref.current.setLookAt(...p.pos, ...p.target, true);
  }, [preset, nonce]);
  useEffect(() => {
    const c = ref.current;
    if (!c || !sel || compact) return;
    let gate: string | null = null;
    if (sel.kind === "gate") gate = sel.id;
    else {
      const f = (scene.userData.flights as Flight[] | undefined)?.find((x) => x.flight_no === sel.id);
      gate = f?.gate ?? null;
    }
    if (!gate) return;
    const s = standPos(gate).pos;
    c.setLookAt(s[0] + 15, 19, s[2] + 21, s[0] - 2, 0.5, s[2] - 2, true);
  }, [sel, compact, scene]);
  void state;
  return (
    <CameraControls ref={ref} makeDefault minDistance={6} maxDistance={190} maxPolarAngle={Math.PI * 0.46}
      smoothTime={0.55} draggingSmoothTime={0.12} />
  );
}

function Lights({ shadows }: { shadows: boolean }) {
  return (
    <>
      <hemisphereLight args={["#9fb8e6", "#0a0f19", 0.55]} />
      <directionalLight position={[48, 70, 34]} intensity={1.9} color="#fff1dd" castShadow={shadows}
        shadow-mapSize={[2048, 2048]} shadow-camera-left={-75} shadow-camera-right={75} shadow-camera-top={70}
        shadow-camera-bottom={-70} shadow-camera-far={220} shadow-bias={-0.0004} shadow-normalBias={0.03} />
      <directionalLight position={[-60, 30, -40]} intensity={0.45} color="#7da2ff" />
      <pointLight position={[0, 2, 13]} intensity={30} distance={40} color="#ffcf8a" />
      <pointLight position={[-26, 2, 13]} intensity={18} distance={28} color="#ffcf8a" />
      <pointLight position={[26, 2, 13]} intensity={18} distance={28} color="#ffcf8a" />
    </>
  );
}

function SceneContent({ state, layout, routes = [], legs = [], compact, highlightGates }: SceneProps) {
  const layers = useTwin((s) => s.layers);
  const simulate = useTwin((s) => s.simulate);
  const focus = useTwin((s) => s.focusRoute);
  const select = useTwin((s) => s.select);
  const { scene } = useThree();
  scene.userData.flights = state.flights;
  const { data: geo } = useQuery<any>({ queryKey: ["geometry"], queryFn: () => get("/web/twin/geometry"), staleTime: Infinity });
  const closed = useMemo(() => new Set(state.closed_edges.map((e) => e.edge_id)), [state.closed_edges]);

  // one aircraft per occupied stand: operating departure > arrival > cancelled departure
  const aircraft = useMemo(() => {
    const byGate = new Map<string, Flight[]>();
    state.flights.forEach((f) => f.gate && byGate.set(f.gate, [...(byGate.get(f.gate) ?? []), f]));
    const out: Flight[] = [];
    byGate.forEach((fl) => {
      const pick = fl.find((f) => f.direction === "DEPARTURE" && f.status !== "CANCELLED") ??
        fl.find((f) => f.direction === "ARRIVAL") ?? fl[0];
      out.push(pick);
    });
    return out;
  }, [state.flights]);
  const occupied = useMemo(() => new Set(aircraft.map((f) => f.gate!)), [aircraft]);
  const hl = highlightGates?.length ? new Set(highlightGates) : null;

  const heat = useMemo(() => {
    if (!layers.heatmap) return [];
    const max = Math.max(1, ...state.flights.map((f) => f.passengers));
    return state.flights.filter((f) => f.gate && f.health !== "normal").map((f) => ({
      pos: standPos(f.gate!).pos, w: Math.min(1, (f.passengers || 1) / max),
      color: f.health === "critical" ? "#f25f5c" : "#f5b544",
    }));
  }, [layers.heatmap, state.flights]);

  return (
    <group onPointerMissed={() => !compact && select(null)}>
      <Ground />
      {geo?.glb_url ? <ApprovedGLB url={geo.glb_url} /> : <MainTerminal roof={layers.roof} />}
      {(["A", "B", "C"] as const).map((c) => <Concourse key={c} c={c} roof={layers.roof} />)}
      {layers.skywalk && <Skywalk closed={closed} />}
      <BaggageHall roof={layers.roof} />
      {!compact && <LightMasts />}
      {state.gates.map((g) => (
        <GateObject key={g.gate} g={g} hasAircraft={layers.aircraft && occupied.has(g.gate)} labels={layers.labels}
          dimmed={hl ? !hl.has(g.gate) : false} />
      ))}
      {layers.aircraft && aircraft.map((f) => (
        <FlightObject key={f.flight_no} f={f} gates={f.gate!} labels={layers.labels && (!hl || hl.has(f.gate!)) && !compact} />
      ))}
      {layers.routes && <PassengerRouteLayer layout={layout} routes={routes} simulate={simulate} focus={focus} closed={closed} />}
      {layers.baggage && <BaggageRouteLayer legs={legs} simulate={simulate} />}
      {layers.heatmap && <Heatmap spots={heat} />}
    </group>
  );
}

export default function AirportScene(props: SceneProps) {
  const [hq, setHq] = useState(!props.compact);
  return (
    <Canvas shadows={hq} dpr={[1, props.compact ? 1.25 : 1.75]} camera={{ fov: 38, near: 0.5, far: 600, position: [62, 66, 58] }}
      gl={{ antialias: false, powerPreference: "high-performance", toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
      onCreated={({ gl }) => { gl.outputColorSpace = THREE.SRGBColorSpace; }}
      aria-label="3D airport digital twin (synthetic, illustrative geometry)">
      <color attach="background" args={["#060a12"]} />
      <fog attach="fog" args={["#060a12", 110, 260]} />
      <PerformanceMonitor onDecline={() => setHq(false)} flipflops={2} />
      <Lights shadows={hq} />
      <Environment resolution={256} frames={1}>
        <Lightformer form="rect" intensity={2.2} position={[0, 30, 0]} rotation-x={Math.PI / 2} scale={[80, 30, 1]} color="#cfe0ff" />
        <Lightformer form="rect" intensity={1.2} position={[60, 12, 0]} rotation-y={-Math.PI / 2} scale={[60, 8, 1]} color="#ffd9a8" />
        <Lightformer form="rect" intensity={0.9} position={[-60, 10, 20]} rotation-y={Math.PI / 2} scale={[60, 6, 1]} color="#8fb0ff" />
        <Lightformer form="ring" intensity={1.5} position={[0, 18, -60]} scale={18} color="#3ec5ff" />
      </Environment>
      <Suspense fallback={null}>
        <SceneContent {...props} />
      </Suspense>
      <CameraRig intro={props.intro} compact={props.compact} />
      {hq ? (
        <EffectComposer multisampling={4} enableNormalPass={false}>
          <N8AO halfRes aoRadius={2.2} intensity={2.4} distanceFalloff={1.2} quality="performance" />
          <Bloom mipmapBlur intensity={0.55} luminanceThreshold={0.82} luminanceSmoothing={0.2} />
          <Vignette darkness={0.55} offset={0.25} />
        </EffectComposer>
      ) : (
        <EffectComposer multisampling={2} enableNormalPass={false}>
          <Bloom mipmapBlur intensity={0.4} luminanceThreshold={0.85} />
        </EffectComposer>
      )}
    </Canvas>
  );
}
