"use client";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import type { BagLeg, Layout, RouteR, TEdge, TNode } from "@/lib/types";
import { bagPoints, edgePoints, pathPoints } from "./layout3d";

function useGraph(layout: Layout) {
  return useMemo(() => {
    const nodes = new Map<string, TNode>(layout.nodes.map((n) => [n.node_id, n]));
    const edges = new Map<string, TEdge>(layout.edges.map((e) => [e.edge_id, e]));
    return { nodes, edges };
  }, [layout]);
}

function Tube({ pts, color, radius = 0.09, opacity = 0.9, dashed = false }: {
  pts: THREE.Vector3[]; color: string; radius?: number; opacity?: number; dashed?: boolean;
}) {
  const geo = useMemo(() => {
    if (pts.length < 2) return null;
    const path = new THREE.CurvePath<THREE.Vector3>();
    for (let i = 0; i < pts.length - 1; i++) path.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    const segs = Math.max(8, Math.round(path.getLength() * 1.5));
    return new THREE.TubeGeometry(path as any, segs, radius, 6, false);
  }, [pts, radius]);
  if (!geo) return null;
  return (
    <mesh geometry={geo} renderOrder={3}>
      <meshBasicMaterial color={color} transparent opacity={dashed ? opacity * 0.55 : opacity} toneMapped={false} depthWrite={false} depthTest={false} />
    </mesh>
  );
}

/** Synthetic movement dots — rendered only while a simulation is active, never as tracking. */
function Dots({ pts, color, count = 6, speed = 9, size = 0.17 }: { pts: THREE.Vector3[]; color: string; count?: number; speed?: number; size?: number }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const path = useMemo(() => {
    if (pts.length < 2) return null;
    const p = new THREE.CurvePath<THREE.Vector3>();
    for (let i = 0; i < pts.length - 1; i++) p.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    return { p, len: p.getLength() };
  }, [pts]);
  const m = useMemo(() => new THREE.Matrix4(), []);
  useFrame(({ clock }) => {
    if (!ref.current || !path) return;
    for (let i = 0; i < count; i++) {
      const t = ((clock.elapsedTime * speed) / path.len + i / count) % 1;
      const v = path.p.getPointAt(t);
      m.makeTranslation(v.x, v.y + 0.12, v.z);
      ref.current.setMatrixAt(i, m);
    }
    ref.current.instanceMatrix.needsUpdate = true;
  });
  if (!path) return null;
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]} renderOrder={4}>
      <sphereGeometry args={[size, 10, 10]} />
      <meshBasicMaterial color={color} toneMapped={false} depthTest={false} transparent />
    </instancedMesh>
  );
}

export function PassengerRouteLayer({ layout, routes, simulate, focus, closed }: {
  layout: Layout; routes: RouteR[]; simulate: boolean; focus: string[] | null; closed: Set<string>;
}) {
  const g = useGraph(layout);
  const items = useMemo(
    () => routes.filter((r) => r.ok && r.node_path && r.edge_path).map((r) => ({
      r, pts: pathPoints(r.node_path!, r.edge_path!, g.edges, g.nodes),
    })),
    [routes, g],
  );
  const focusPts = useMemo(() => {
    if (!focus || focus.length < 2) return null;
    const ep: string[] = [];
    for (let i = 0; i < focus.length - 1; i++) {
      const e = layout.edges.find((x) => (x.from_node === focus[i] && x.to_node === focus[i + 1]) || (x.to_node === focus[i] && x.from_node === focus[i + 1]));
      if (e) ep.push(e.edge_id);
    }
    return pathPoints(focus, ep, g.edges, g.nodes);
  }, [focus, layout, g]);
  return (
    <group>
      {items.map(({ r, pts }, i) => {
        const access = r.profile !== "STANDARD";
        const color = access ? "#7ee0ff" : "#3ec5ff";
        return (
          <group key={`${r.from}-${r.to}-${r.profile}-${i}`}>
            <Tube pts={pts} color={color} radius={access ? 0.075 : 0.06} opacity={focus ? 0.25 : 0.7} />
            {simulate && <Dots pts={pts} color="#bfefff" count={access ? 3 : 5} speed={access ? 5 : 8} size={0.14} />}
          </group>
        );
      })}
      {focusPts && (
        <group>
          <Tube pts={focusPts} color="#ffffff" radius={0.12} opacity={0.95} />
          <Dots pts={focusPts} color="#3ec5ff" count={8} speed={10} size={0.2} />
        </group>
      )}
      {/* closed corridors in red */}
      {layout.edges.filter((e) => closed.has(e.edge_id)).map((e) => (
        <Tube key={e.edge_id} pts={edgePoints(e, e.from_node, g.nodes)} color="#f25f5c" radius={0.22} opacity={0.95} />
      ))}
    </group>
  );
}

export function BaggageRouteLayer({ legs, simulate }: { legs: BagLeg[]; simulate: boolean }) {
  const items = useMemo(() => legs.map((l) => ({ l, pts: bagPoints(l.from_gate, l.to_gate) })), [legs]);
  return (
    <group>
      {items.map(({ l, pts }, i) => {
        const color = l.discrepancy ? "#f5b544" : "#8aa4c2";
        return (
          <group key={i}>
            <Tube pts={pts} color={color} radius={l.discrepancy ? 0.1 : 0.05} opacity={l.discrepancy ? 0.95 : 0.45} dashed={!l.discrepancy} />
            {simulate && <BagBoxes pts={pts} color={color} count={Math.min(6, l.bags.length)} />}
          </group>
        );
      })}
    </group>
  );
}

function BagBoxes({ pts, color, count }: { pts: THREE.Vector3[]; color: string; count: number }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const path = useMemo(() => {
    const p = new THREE.CurvePath<THREE.Vector3>();
    for (let i = 0; i < pts.length - 1; i++) p.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    return { p, len: p.getLength() };
  }, [pts]);
  const m = useMemo(() => new THREE.Matrix4(), []);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    for (let i = 0; i < count; i++) {
      const t = ((clock.elapsedTime * 6) / path.len + i / Math.max(1, count) * 0.25) % 1;
      const v = path.p.getPointAt(t);
      m.makeTranslation(v.x, v.y + 0.18, v.z);
      ref.current.setMatrixAt(i, m);
    }
    ref.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, Math.max(1, count)]}>
      <boxGeometry args={[0.32, 0.22, 0.42]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
    </instancedMesh>
  );
}

/** Disruption heatmap: soft discs at stands, intensity from affected passengers (backend counts). */
export function Heatmap({ spots }: { spots: { pos: [number, number, number]; w: number; color: string }[] }) {
  const tex = useMemo(() => {
    if (typeof document === "undefined") return null;
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const g = c.getContext("2d")!;
    const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, "rgba(255,255,255,1)");
    gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr;
    g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }, []);
  return (
    <group>
      {spots.map((s, i) => (
        <mesh key={i} rotation-x={-Math.PI / 2} position={[s.pos[0], 0.04, s.pos[2]]} renderOrder={2}>
          <planeGeometry args={[4 + s.w * 9, 4 + s.w * 9]} />
          <meshBasicMaterial map={tex ?? undefined} color={s.color} transparent opacity={0.35 + s.w * 0.4}
            blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}
