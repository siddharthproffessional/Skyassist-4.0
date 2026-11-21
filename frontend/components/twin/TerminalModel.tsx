"use client";
import { useMemo } from "react";
import * as THREE from "three";
import { Text } from "@react-three/drei";
import { CONC_GATES, CONC_X, HALL, HUB_Z, OUTER_Z, PIER_HALF, PITCH, SKY_Y, SKY_Z, TERMINAL, gateZ } from "./layout3d";
import { M, concreteTexture } from "./materials";

export const FONT = "/fonts/inter-600.woff";
const MONO = "/fonts/jbm-500.woff";

function Box({ p, s, m, cast = true, receive = true, ...rest }: any) {
  return (
    <mesh position={p} castShadow={cast} receiveShadow={receive} material={m} {...rest}>
      <boxGeometry args={s} />
    </mesh>
  );
}

/* ---------------------------------------------------------------- ground: apron, runway, taxiways */
export function Ground() {
  const apron = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({ color: "#ffffff", map: concreteTexture() ?? undefined, roughness: 0.92, metalness: 0.05 });
    return m;
  }, []);
  const dashes = useMemo(() => Array.from({ length: 30 }, (_, i) => -72 + i * 5), []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.02, -8]} receiveShadow material={M.grass}>
        <planeGeometry args={[340, 300]} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0, -16]} receiveShadow material={apron}>
        <planeGeometry args={[100, 84]} />
      </mesh>
      {/* runway + parallel taxiway (illustrative) */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.005, -71]} receiveShadow material={M.asphalt}>
        <planeGeometry args={[170, 7]} />
      </mesh>
      {dashes.map((x) => (
        <mesh key={x} rotation-x={-Math.PI / 2} position={[x, 0.012, -71]} material={M.markingWhite}>
          <planeGeometry args={[2.6, 0.18]} />
        </mesh>
      ))}
      {[-82, -80.6, -79.2, 79.2, 80.6, 82].map((x) => (
        <mesh key={x} rotation-x={-Math.PI / 2} position={[x, 0.012, -71]} material={M.markingWhite}>
          <planeGeometry args={[0.6, 5.4]} />
        </mesh>
      ))}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.004, -62]} receiveShadow material={M.asphalt}>
        <planeGeometry args={[150, 4]} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.013, -62]} material={M.marking}>
        <planeGeometry args={[150, 0.12]} />
      </mesh>
      {/* taxilanes between piers */}
      {[-39, -13, 13, 39].map((x) => (
        <mesh key={x} rotation-x={-Math.PI / 2} position={[x, 0.013, -26]} material={M.marking}>
          <planeGeometry args={[0.12, 72]} />
        </mesh>
      ))}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.013, 7.2]} material={M.markingWhite}>
        <planeGeometry args={[88, 0.1]} />
      </mesh>
      {/* landside road */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.006, 37]} receiveShadow material={M.asphalt}>
        <planeGeometry args={[120, 6]} />
      </mesh>
      <Text font={MONO} fontSize={1.1} color="#4b5a70" rotation={[-Math.PI / 2, 0, 0]} position={[-60, 0.02, -74.5]} anchorX="left">
        RWY 12/30 · ILLUSTRATIVE
      </Text>
    </group>
  );
}

/* ---------------------------------------------------------------- main terminal with an arched roof */
export function MainTerminal({ roof }: { roof: boolean }) {
  const { x0, x1, z0, z1, h } = TERMINAL;
  const w = x1 - x0, d = z1 - z0, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  const roofGeo = useMemo(() => {
    const R = 13, half = Math.asin((d / 2 + 0.6) / R);
    const g = new THREE.CylinderGeometry(R, R, w + 2, 72, 1, true, Math.PI / 2 - half, half * 2);
    g.rotateZ(Math.PI / 2);
    g.translate(0, -R * Math.cos(half), 0);
    return g;
  }, [w, d]);
  const ribs = useMemo(() => Array.from({ length: Math.floor(w / 4) + 1 }, (_, i) => x0 + i * 4), [w, x0]);
  return (
    <group>
      <Box p={[cx, 0.06, cz]} s={[w, 0.12, d]} m={M.floor} cast={false} />
      <Box p={[cx, 0.13, cz]} s={[w - 1, 0.02, d - 1]} m={M.floorWarm} cast={false} />
      {/* façades */}
      <mesh position={[cx, h / 2, z0]} material={M.glass}><planeGeometry args={[w, h]} /></mesh>
      <mesh position={[cx, h / 2, z1]} material={M.glass}><planeGeometry args={[w, h]} /></mesh>
      <mesh position={[x0, h / 2, cz]} rotation-y={Math.PI / 2} material={M.glass}><planeGeometry args={[d, h]} /></mesh>
      <mesh position={[x1, h / 2, cz]} rotation-y={Math.PI / 2} material={M.glass}><planeGeometry args={[d, h]} /></mesh>
      {/* mullions */}
      {ribs.map((x) => (
        <group key={x}>
          <Box p={[x, h / 2, z0]} s={[0.07, h, 0.07]} m={M.structure} receive={false} />
          <Box p={[x, h / 2, z1]} s={[0.07, h, 0.07]} m={M.structure} receive={false} />
        </group>
      ))}
      {roof && (
        <group position={[cx, h + 0.15, cz]}>
          <mesh geometry={roofGeo} material={M.roof} castShadow receiveShadow />
          {[-1.6, 1.6].map((z) => (
            <mesh key={z} position={[0, 0.62, z]} material={M.glassDark}>
              <boxGeometry args={[w - 4, 0.06, 0.9]} />
            </mesh>
          ))}
        </group>
      )}
      {/* check-in islands / interior hints */}
      {[-30, -18, 18, 30].map((x) => (
        <Box key={x} p={[x, 0.45, 15.2]} s={[5, 0.6, 0.8]} m={M.structure} />
      ))}
      <Text font={FONT} fontSize={0.9} letterSpacing={0.18} color="#9fb3cc" position={[0, 0.16, 15.6]} rotation={[-Math.PI / 2, 0, 0]}>
        MAIN TERMINAL · LEVEL 1
      </Text>
    </group>
  );
}

/* ---------------------------------------------------------------- piers (concourses A, B, C) */
export function Concourse({ c, roof }: { c: "A" | "B" | "C"; roof: boolean }) {
  const cx = CONC_X[c];
  const n = CONC_GATES[c];
  const zEnd = gateZ(`${c}${String(n).padStart(2, "0")}`) - 1.6;
  const z0 = TERMINAL.z0;
  const len = z0 - zEnd;
  const zc = (z0 + zEnd) / 2;
  const h = 1.3;
  const fins = useMemo(() => Array.from({ length: Math.floor(len / PITCH) }, (_, i) => z0 - i * PITCH), [len, z0]);
  return (
    <group>
      <Box p={[cx, 0.05, zc]} s={[PIER_HALF * 2, 0.1, len]} m={M.floor} cast={false} />
      {/* walkway light strip = the routed corridor */}
      <Box p={[cx, 0.11, zc]} s={[0.18, 0.012, len - 0.6]} m={new THREE.MeshBasicMaterial({ color: "#3ec5ff", transparent: true, opacity: 0.35 })} cast={false} receive={false} />
      <mesh position={[cx - PIER_HALF, h / 2, zc]} rotation-y={Math.PI / 2} material={M.glass}><planeGeometry args={[len, h]} /></mesh>
      <mesh position={[cx + PIER_HALF, h / 2, zc]} rotation-y={Math.PI / 2} material={M.glass}><planeGeometry args={[len, h]} /></mesh>
      <mesh position={[cx, h / 2, zEnd]} material={M.glass}><planeGeometry args={[PIER_HALF * 2, h]} /></mesh>
      {fins.map((z) => (
        <group key={z}>
          <Box p={[cx - PIER_HALF, h / 2, z]} s={[0.06, h, 0.06]} m={M.structure} receive={false} />
          <Box p={[cx + PIER_HALF, h / 2, z]} s={[0.06, h, 0.06]} m={M.structure} receive={false} />
        </group>
      ))}
      {roof && <Box p={[cx, h + 0.06, zc]} s={[PIER_HALF * 2 + 0.5, 0.12, len + 0.3]} m={M.roof} />}
      {roof && <Box p={[cx, h + 0.16, zc]} s={[0.9, 0.1, len - 1]} m={M.glassDark} />}
      <Text font={FONT} fontSize={1.5} letterSpacing={0.24} color="#c8d6e8" position={[cx, 0.03, zEnd - 3.4]}
        rotation={[-Math.PI / 2, 0, 0]} outlineWidth={0.02} outlineColor="#060a12">
        {`CONCOURSE ${c}`}
      </Text>
      {/* hub landmarks: transfer security, transfer desk, special assistance */}
      <group>
        <Box p={[cx - 2.8, 0.35, 11.4]} s={[1.4, 0.5, 0.8]} m={M.structure} />
        <Box p={[cx - 2.8, 0.62, 11.4]} s={[1.4, 0.04, 0.8]} m={new THREE.MeshBasicMaterial({ color: "#f5b544" })} cast={false} />
        <Box p={[cx + 2.8, 0.35, 10.9]} s={[1.2, 0.5, 0.6]} m={M.structure} />
        <Box p={[cx + 2.8, 0.62, 10.9]} s={[1.2, 0.04, 0.6]} m={new THREE.MeshBasicMaterial({ color: "#3ec5ff" })} cast={false} />
        <Box p={[cx + 2.8, 0.35, 12.6]} s={[1.2, 0.5, 0.6]} m={M.structure} />
        <Box p={[cx + 2.8, 0.62, 12.6]} s={[1.2, 0.04, 0.6]} m={new THREE.MeshBasicMaterial({ color: "#a78bfa" })} cast={false} />
      </group>
      {/* vertical circulation core: lift + escalator to Level 2 skywalk */}
      <Box p={[cx + 0.9, SKY_Y / 2, SKY_Z]} s={[0.9, SKY_Y, 0.9]} m={M.glassDark} />
      <mesh position={[cx - 0.9, SKY_Y / 2, SKY_Z - 0.4]} rotation-x={-0.62} material={M.structure} castShadow>
        <boxGeometry args={[0.7, 0.12, 5.4]} />
      </mesh>
    </group>
  );
}

/* ---------------------------------------------------------------- Level 2 skywalk, service corridor, mezzanine */
export function Skywalk({ closed }: { closed: Set<string> }) {
  const seg = (xa: number, xb: number, id: string) => {
    const len = Math.abs(xb - xa);
    const red = closed.has(id);
    return (
      <group key={id} position={[(xa + xb) / 2, SKY_Y, SKY_Z]}>
        <mesh rotation-z={Math.PI / 2} material={red ? new THREE.MeshPhysicalMaterial({ color: "#f25f5c", transparent: true, opacity: 0.55, emissive: "#f25f5c", emissiveIntensity: 0.6 }) : M.glass} castShadow>
          <cylinderGeometry args={[0.62, 0.62, len, 24, 1, true]} />
        </mesh>
        <mesh position={[0, -0.5, 0]} castShadow receiveShadow material={M.structure}>
          <boxGeometry args={[len, 0.12, 1.1]} />
        </mesh>
        <mesh position={[0, -0.42, 0]} material={new THREE.MeshBasicMaterial({ color: red ? "#f25f5c" : "#3ec5ff", transparent: true, opacity: 0.45 })}>
          <boxGeometry args={[len, 0.01, 0.12]} />
        </mesh>
      </group>
    );
  };
  const outerRed = closed.has("E_OUTER_AC");
  const stairsRed = closed.has("E_STAIRS_B03_C08");
  const zb = gateZ("B03"), zc = gateZ("C08");
  const a = new THREE.Vector3(CONC_X.B + 2.2, 3.1, zb), b = new THREE.Vector3(CONC_X.C - 2.2, 3.1, zc);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const len = a.distanceTo(b);
  const ang = Math.atan2(b.x - a.x, b.z - a.z);
  const outerMat = outerRed ? new THREE.MeshStandardMaterial({ color: "#f25f5c", emissive: "#f25f5c", emissiveIntensity: 0.5 }) : M.roofDark;
  return (
    <group>
      {seg(CONC_X.A, CONC_X.B, "E_SKY_AB")}
      {seg(CONC_X.B, CONC_X.C, "E_SKY_BC")}
      {/* outer service corridor A–C (step-free cart lane, Level 2) */}
      <Box p={[0, SKY_Y - 0.25, OUTER_Z]} s={[CONC_X.C - CONC_X.A, 0.6, 1.2]} m={outerMat} />
      <Box p={[CONC_X.A, SKY_Y - 0.25, (SKY_Z + OUTER_Z) / 2]} s={[1.2, 0.6, OUTER_Z - SKY_Z]} m={outerMat} />
      <Box p={[CONC_X.C, SKY_Y - 0.25, (SKY_Z + OUTER_Z) / 2]} s={[1.2, 0.6, OUTER_Z - SKY_Z]} m={outerMat} />
      {/* mezzanine stairway B03 → C08 (stairs only) */}
      <group position={mid.toArray()} rotation-y={ang}>
        <mesh castShadow material={stairsRed ? new THREE.MeshStandardMaterial({ color: "#f25f5c", emissive: "#f25f5c", emissiveIntensity: 0.5 }) : M.structure}>
          <boxGeometry args={[0.9, 0.14, len]} />
        </mesh>
        <mesh position={[0.45, 0.35, 0]} material={M.glass}><boxGeometry args={[0.02, 0.6, len]} /></mesh>
        <mesh position={[-0.45, 0.35, 0]} material={M.glass}><boxGeometry args={[0.02, 0.6, len]} /></mesh>
      </group>
      {[a, b].map((v, i) => (
        <Box key={i} p={[v.x, 1.55, v.z]} s={[0.25, 3.1, 0.25]} m={M.structure} />
      ))}
      <Text font={FONT} fontSize={0.55} color="#7f93ad" position={[(CONC_X.A + CONC_X.B) / 2, SKY_Y + 0.9, SKY_Z]} letterSpacing={0.12}>
        SKYWALK A–B · LEVEL 2 · 500 m
      </Text>
      <Text font={FONT} fontSize={0.55} color="#7f93ad" position={[(CONC_X.B + CONC_X.C) / 2, SKY_Y + 0.9, SKY_Z]} letterSpacing={0.12}>
        SKYWALK B–C · LEVEL 2 · 600 m
      </Text>
    </group>
  );
}

/* ---------------------------------------------------------------- baggage hall (transfer sortation) */
export function BaggageHall({ roof }: { roof: boolean }) {
  const { x0, x1, z0, z1 } = HALL;
  const loop = useMemo(() => {
    const pts = [[-12, 26], [12, 26], [14, 28], [12, 30], [-12, 30], [-14, 28]].map(([x, z]) => new THREE.Vector3(x, 0.45, z));
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, true, "catmullrom", 0.2), 160, 0.22, 8, true);
  }, []);
  return (
    <group>
      <Box p={[(x0 + x1) / 2, 0.05, (z0 + z1) / 2]} s={[x1 - x0, 0.1, z1 - z0]} m={M.floor} cast={false} />
      <mesh position={[(x0 + x1) / 2, 0.9, z0]} material={M.glass}><planeGeometry args={[x1 - x0, 1.8]} /></mesh>
      <mesh position={[(x0 + x1) / 2, 0.9, z1]} material={M.glass}><planeGeometry args={[x1 - x0, 1.8]} /></mesh>
      {roof && <Box p={[(x0 + x1) / 2, 1.85, (z0 + z1) / 2]} s={[x1 - x0, 0.1, z1 - z0]} m={M.roofDark} />}
      <mesh geometry={loop} material={M.conveyor} castShadow />
      {[-8, -3, 3, 8].map((x) => (
        <Box key={x} p={[x, 0.3, 28]} s={[2.2, 0.5, 0.9]} m={M.structure} />
      ))}
      <Text font={FONT} fontSize={0.8} letterSpacing={0.18} color="#c9a66b" position={[0, 0.13, 32.9]} rotation={[-Math.PI / 2, 0, 0]}>
        BAGGAGE · TRANSFER SORTATION
      </Text>
    </group>
  );
}

/* ---------------------------------------------------------------- apron flood-light masts (ambient) */
export function LightMasts() {
  const masts = useMemo(() => {
    const out: [number, number][] = [];
    for (const x of [-39, -13, 13, 39]) for (const z of [-8, -28, -48]) out.push([x, z]);
    return out;
  }, []);
  return (
    <group>
      {masts.map(([x, z]) => (
        <group key={`${x}${z}`} position={[x, 0, z]}>
          <mesh position={[0, 3.2, 0]} castShadow material={M.structure}><cylinderGeometry args={[0.06, 0.09, 6.4, 8]} /></mesh>
          <mesh position={[0, 6.45, 0]} material={new THREE.MeshBasicMaterial({ color: "#fff3d6" })}><boxGeometry args={[0.7, 0.12, 0.3]} /></mesh>
        </group>
      ))}
    </group>
  );
}

export { HUB_Z };
