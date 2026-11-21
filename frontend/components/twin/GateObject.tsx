"use client";
import { useRef, useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Text } from "@react-three/drei";
import type { Gate } from "@/lib/types";
import { GATE_COLOR } from "@/lib/colors";
import { useTwin } from "@/lib/store";
import { PIER_HALF, gateSide, podPos, standPos } from "./layout3d";
import { M } from "./materials";
import { FONT } from "./TerminalModel";

const SHORT: Record<string, string> = {
  AVAILABLE: "", OCCUPIED: "", BOARDING: "BOARDING", DEPARTING: "DEPARTING", BLOCKED: "BLOCKED",
  UNDER_REVIEW: "REVIEW", PENDING_APPROVAL: "APPROVAL",
};

export default function GateObject({ g, hasAircraft, labels, dimmed }: { g: Gate; hasAircraft: boolean; labels: boolean; dimmed?: boolean }) {
  const sel = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  const selected = sel?.kind === "gate" && sel.id === g.gate;
  const [hover, setHover] = useState(false);
  const ring = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const pod = podPos(g.gate);
  const st = standPos(g.gate);
  const side = gateSide(g.gate);
  const color = g.cancelled.length && g.status === "AVAILABLE" ? "#f25f5c" : GATE_COLOR[g.status];
  const alerting = g.status === "PENDING_APPROVAL" || g.status === "BLOCKED" || g.status === "UNDER_REVIEW" || g.affected;

  useFrame(({ clock }) => {
    if (halo.current) {
      const t = (clock.elapsedTime * 0.7) % 1;
      halo.current.scale.setScalar(1 + t * 0.6);
      (halo.current.material as THREE.MeshBasicMaterial).opacity = (1 - t) * 0.55;
    }
  });

  const onClick = (e: any) => {
    e.stopPropagation();
    select({ kind: "gate", id: g.gate });
  };
  const bridgeLen = Math.abs(st.nose[0] - (pod[0] + side * 0.55)) + 0.2;
  const bridgeX = (st.nose[0] + pod[0] + side * 0.55) / 2;

  return (
    <group>
      {/* holdroom pod */}
      <mesh position={[pod[0], 0.55, pod[2]]} castShadow receiveShadow material={M.glassDark}
        onClick={onClick} onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}>
        <boxGeometry args={[1.1, 1.0, 1.7]} />
      </mesh>
      <mesh position={[pod[0], 1.08, pod[2]]} material={M.roof} castShadow>
        <boxGeometry args={[1.2, 0.06, 1.8]} />
      </mesh>
      {/* status light strip on the pod (colour) */}
      <mesh position={[pod[0] + side * 0.56, 0.95, pod[2]]}>
        <boxGeometry args={[0.03, 0.08, 1.5]} />
        <meshBasicMaterial color={color} toneMapped={false} />
      </mesh>
      {/* boarding bridge */}
      {hasAircraft && (
        <group position={[bridgeX, 0.62, pod[2] - 0.75]}>
          <mesh castShadow material={M.bridge}><boxGeometry args={[bridgeLen, 0.32, 0.36]} /></mesh>
          <mesh position={[side * (bridgeLen / 2 - 0.3), -0.33, 0]} material={M.structure} castShadow>
            <cylinderGeometry args={[0.05, 0.05, 0.62, 6]} />
          </mesh>
        </group>
      )}
      {/* stand: lead-in line + status ring (clickable) */}
      <mesh rotation-x={-Math.PI / 2} position={[st.pos[0] + side * 1.8, 0.014, st.pos[2]]} material={M.marking}>
        <planeGeometry args={[6, 0.07]} />
      </mesh>
      <mesh ref={ring} rotation-x={-Math.PI / 2} position={[st.pos[0], 0.02, st.pos[2]]} onClick={onClick}>
        <ringGeometry args={[2.05, selected ? 2.45 : 2.22, 48]} />
        <meshBasicMaterial color={selected ? "#ffffff" : color} transparent opacity={dimmed ? 0.15 : g.status === "AVAILABLE" && !g.cancelled.length ? 0.35 : 0.85} toneMapped={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[st.pos[0], 0.016, st.pos[2]]} onClick={onClick}>
        <circleGeometry args={[2.05, 40]} />
        <meshBasicMaterial color={color} transparent opacity={hover || selected ? 0.16 : g.status === "AVAILABLE" ? 0.02 : 0.06} toneMapped={false} />
      </mesh>
      {alerting && !dimmed && (
        <mesh ref={halo} rotation-x={-Math.PI / 2} position={[st.pos[0], 0.03, st.pos[2]]}>
          <ringGeometry args={[2.25, 2.4, 48]} />
          <meshBasicMaterial color={color} transparent opacity={0.5} toneMapped={false} />
        </mesh>
      )}
      {labels && (
        <group position={[pod[0], 1.5, pod[2]]}>
          <Text font={FONT} fontSize={0.42} color={selected ? "#ffffff" : "#d6e2f0"} rotation={[-Math.PI / 2, 0, 0]}
            anchorX="center" anchorY="middle" outlineWidth={0.015} outlineColor="#060a12">
            {g.gate}
          </Text>
        </group>
      )}
      {labels && SHORT[g.status] && (
        <Text font={FONT} fontSize={0.36} color={color} rotation={[-Math.PI / 2, 0, side > 0 ? -Math.PI / 2 : Math.PI / 2]}
          position={[st.pos[0] + side * (PIER_HALF - 0.4), 0.03, st.pos[2]]} letterSpacing={0.1}>
          {SHORT[g.status]}
        </Text>
      )}
    </group>
  );
}
