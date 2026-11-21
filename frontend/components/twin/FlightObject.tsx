"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import type { Flight } from "@/lib/types";
import { HEALTH_COLOR } from "@/lib/colors";
import { useTwin } from "@/lib/store";
import { aircraftGeometry } from "./aircraftGeometry";
import { CONC_X, gateSide, standPos } from "./layout3d";
import { M } from "./materials";

const ghost = new THREE.MeshStandardMaterial({ color: "#f25f5c", transparent: true, opacity: 0.32, emissive: "#f25f5c", emissiveIntensity: 0.25, depthWrite: false });
const amberBody = new THREE.MeshPhysicalMaterial({ color: "#f3e3c0", metalness: 0.15, roughness: 0.32, clearcoat: 0.7, emissive: "#f5b544", emissiveIntensity: 0.08 });
const redBody = new THREE.MeshPhysicalMaterial({ color: "#f3d0cf", metalness: 0.15, roughness: 0.32, clearcoat: 0.7, emissive: "#f25f5c", emissiveIntensity: 0.12 });

/** Illustrative ground path between two stands (taxilanes + pier-end taxiway). NOT ATC guidance. */
function groundPath(from: string, to: string): THREE.Vector3[] {
  const lane = (g: string) => CONC_X[g[0]] + gateSide(g) * 13;
  const a = standPos(from), b = standPos(to);
  const la = lane(from), lb = lane(to);
  const pts = [new THREE.Vector3(...a.pos), new THREE.Vector3(la, 0, a.pos[2])];
  if (la !== lb) {
    pts.push(new THREE.Vector3(la, 0, -62), new THREE.Vector3(lb, 0, -62));
  }
  pts.push(new THREE.Vector3(lb, 0, b.pos[2]), new THREE.Vector3(...b.pos));
  return pts;
}

export default function FlightObject({ f, gates, labels }: { f: Flight; gates: string; labels: boolean }) {
  const geo = useMemo(() => aircraftGeometry(), []);
  const sel = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  const selected = sel?.kind === "flight" && sel.id === f.flight_no;
  const group = useRef<THREE.Group>(null);
  const beacon = useRef<THREE.Mesh>(null);
  const [hover, setHover] = useState(false);
  const gate = f.gate!;
  const target = standPos(gate);
  const anim = useRef<{ curve: THREE.CurvePath<THREE.Vector3>; t: number; len: number } | null>(null);
  const lastGate = useRef<string>(gate);
  const [moving, setMoving] = useState(false);

  // When the authoritative gate changes (e.g. an approved, executed gate move), animate along an illustrative path.
  useEffect(() => {
    if (lastGate.current !== gate && group.current) {
      const pts = groundPath(lastGate.current, gate);
      const path = new THREE.CurvePath<THREE.Vector3>();
      for (let i = 0; i < pts.length - 1; i++) path.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
      anim.current = { curve: path, t: 0, len: path.getLength() };
      setMoving(true);
    }
    lastGate.current = gate;
  }, [gate]);

  useFrame(({ clock }, dt) => {
    const g = group.current;
    if (!g) return;
    if (anim.current) {
      const a = anim.current;
      a.t = Math.min(1, a.t + (dt * 14) / a.len);
      const e = a.t < 0.5 ? 2 * a.t * a.t : 1 - Math.pow(-2 * a.t + 2, 2) / 2;
      const p = a.curve.getPointAt(e);
      const ahead = a.curve.getPointAt(Math.min(1, e + 0.002));
      g.position.copy(p);
      if (ahead.distanceTo(p) > 1e-4) {
        const yaw = Math.atan2(ahead.x - p.x, ahead.z - p.z) + Math.PI; // nose is −Z
        g.rotation.y = yaw;
      }
      if (a.t >= 1) {
        anim.current = null;
        g.position.set(...target.pos);
        g.rotation.y = target.rotY;
        setMoving(false);
      }
    }
    if (beacon.current) {
      const on = Math.sin(clock.elapsedTime * 6 + f.flight_no.length) > 0.86;
      (beacon.current.material as THREE.MeshBasicMaterial).opacity = on ? 1 : 0.08;
    }
  });

  const cancelled = f.status === "CANCELLED";
  const bodyMat = cancelled ? ghost : f.health === "critical" ? redBody : f.health === "warning" ? amberBody : M.white;
  const color = HEALTH_COLOR[f.health];
  const showTag = labels && (f.health !== "normal" || selected || hover || moving);
  const onClick = (e: any) => {
    e.stopPropagation();
    select({ kind: "flight", id: f.flight_no });
  };

  return (
    <group ref={group} position={target.pos} rotation-y={target.rotY}>
      <group onClick={onClick}
        onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}
        scale={selected ? 1.04 : 1}>
        <mesh geometry={geo.body} material={bodyMat} castShadow={!cancelled} receiveShadow />
        <mesh geometry={geo.fin} material={cancelled ? ghost : M.fin} castShadow={!cancelled} />
        <mesh geometry={geo.engines} material={cancelled ? ghost : M.metal} castShadow={!cancelled} />
        <mesh geometry={geo.glass} material={M.cockpit} />
        <mesh ref={beacon} position={[0, 0.9, 0.1]}>
          <sphereGeometry args={[0.05, 8, 8]} />
          <meshBasicMaterial color="#ff3b3b" transparent toneMapped={false} />
        </mesh>
        {/* invisible hit area for easier picking */}
        <mesh visible={false}>
          <boxGeometry args={[4.6, 1.4, 4.8]} />
        </mesh>
      </group>
      {showTag && (
        <Html position={[0, 2.0, 0]} center zIndexRange={[6, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-md px-2 py-1 text-[11px] leading-tight shadow-lg"
            style={{ background: "rgba(6,10,18,0.88)", borderLeft: `3px solid ${color}`, boxShadow: "0 4px 18px rgba(0,0,0,.5)" }}>
            <div className="mono font-semibold text-white">{f.flight_no} {f.direction === "DEPARTURE" ? "→ " + f.destination : "← " + f.origin}</div>
            <div className="font-semibold tracking-wide text-[9.5px]" style={{ color }}>
              {moving ? "MOVING · ILLUSTRATIVE PATH" : (f.reasons[0] ?? f.status.replace(/_/g, " ")).toUpperCase()}
            </div>
          </div>
        </Html>
      )}
    </group>
  );
}
