/**
 * ILLUSTRATIVE 3D placement derived from the SkyAssist routing graph.
 *
 * - Topology (which gate is on which concourse, gate order, which nodes connect) comes from terminal_nodes /
 *   terminal_edges exactly. Nothing here adds or removes a connection.
 * - Distances shown to users always come from edge lengths (distance_m), never from these coordinates.
 * - Gates alternate sides of their pier so that aircraft fit; this is a visual convention, not surveyed data.
 */
import * as THREE from "three";
import type { TEdge, TNode } from "@/lib/types";

export const CONC_X: Record<string, number> = { A: -26, B: 0, C: 26 };
export const CONC_GATES: Record<string, number> = { A: 20, B: 20, C: 22 };
export const HUB_Z = 8.6;
export const PITCH = 2.6;
export const PIER_HALF = 1.7;
export const TERMINAL = { x0: -37, x1: 37, z0: 9.2, z1: 17.2, h: 2.5 };
export const SKY_Y = 3.55;
export const SKY_Z = 13.2;
export const OUTER_Z = 21;
export const HALL = { x0: -18, x1: 18, z0: 24, z1: 32 };
export const APRON_ROAD_Z = 7.2;

export const gateNum = (gate: string) => parseInt(gate.slice(1), 10);
export const gateSide = (gate: string) => (gateNum(gate) % 2 === 1 ? -1 : 1);
export const gateZ = (gate: string) => HUB_Z - 2.6 - (gateNum(gate) - 1) * PITCH;

/** Holdroom pod on the pier edge. */
export function podPos(gate: string): [number, number, number] {
  const cx = CONC_X[gate[0]];
  return [cx + gateSide(gate) * (PIER_HALF + 0.55), 0, gateZ(gate)];
}

/** Aircraft stand centre and heading (nose points at the pier). */
export function standPos(gate: string): { pos: [number, number, number]; rotY: number; nose: [number, number, number] } {
  const cx = CONC_X[gate[0]];
  const s = gateSide(gate);
  const half = 2.45;
  const noseX = cx + s * (PIER_HALF + 1.45);
  const x = noseX + s * half;
  return { pos: [x, 0, gateZ(gate)], rotY: s > 0 ? Math.PI / 2 : -Math.PI / 2, nose: [noseX, 0, gateZ(gate)] };
}

/** Position of a graph node for route lines (walking level y≈0.35, Level 2 at SKY_Y). */
export function nodePos(n: TNode | undefined, id: string): THREE.Vector3 {
  const c = (n?.concourse ?? id.split("_")[1]?.[0] ?? "B") as string;
  const cx = CONC_X[c] ?? 0;
  if (id.startsWith("G_")) return new THREE.Vector3(cx, 0.38, gateZ(id.slice(2)));
  if (id.startsWith("HUB_")) return new THREE.Vector3(cx, 0.38, HUB_Z + 1.2);
  if (id.startsWith("CON_")) return new THREE.Vector3(cx, SKY_Y, SKY_Z);
  if (id.startsWith("SEC_")) return new THREE.Vector3(cx - 2.8, 0.38, 11.4);
  if (id.startsWith("TD_")) return new THREE.Vector3(cx + 2.8, 0.38, 10.9);
  if (id.startsWith("AP_")) return new THREE.Vector3(cx + 2.8, 0.38, 12.6);
  return new THREE.Vector3(cx, 0.38, HUB_Z);
}

/** Way-points of one edge traversed from `from` to `to`, including special geometry edges. */
export function edgePoints(e: TEdge, from: string, nodes: Map<string, TNode>): THREE.Vector3[] {
  const a = nodePos(nodes.get(from), from);
  const toId = e.from_node === from ? e.to_node : e.from_node;
  const b = nodePos(nodes.get(toId), toId);
  let mid: THREE.Vector3[] = [];
  if (e.edge_id === "E_OUTER_AC") {
    mid = [new THREE.Vector3(CONC_X.A, SKY_Y, OUTER_Z), new THREE.Vector3(CONC_X.C, SKY_Y, OUTER_Z)];
    if (from === "CON_C") mid.reverse();
  } else if (e.edge_id === "E_STAIRS_B03_C08") {
    const zb = gateZ("B03"), zc = gateZ("C08");
    mid = [new THREE.Vector3(CONC_X.B + 2.2, 3.1, zb), new THREE.Vector3(CONC_X.C - 2.2, 3.1, zc)];
    if (from === "G_C08") mid.reverse();
  } else if (e.kind === "VERTICAL") {
    mid = [new THREE.Vector3(a.x + (e.elevator ? 0.9 : -0.9), (a.y + b.y) / 2, (a.z + b.z) / 2)];
  }
  return [a, ...mid, b];
}

export function pathPoints(nodePath: string[], edgePath: string[], edges: Map<string, TEdge>, nodes: Map<string, TNode>) {
  const pts: THREE.Vector3[] = [];
  edgePath.forEach((eid, i) => {
    const e = edges.get(eid);
    if (!e) return;
    const seg = edgePoints(e, nodePath[i], nodes);
    if (pts.length) seg.shift();
    pts.push(...seg);
  });
  return pts;
}

/** Baggage leg: inbound stand → apron road → under the terminal to transfer sortation → departure stand. */
export function bagPoints(fromGate: string | null, toGate: string | null): THREE.Vector3[] {
  const hall = new THREE.Vector3(0, 0.12, (HALL.z0 + HALL.z1) / 2);
  const leg = (g: string, toward: boolean) => {
    const s = standPos(g).pos;
    const p = [
      new THREE.Vector3(s[0], 0.12, s[2]),
      new THREE.Vector3(s[0], 0.12, APRON_ROAD_Z),
      new THREE.Vector3(CONC_X[g[0]] + (g[0] === "B" ? 4.2 : g[0] === "A" ? 4.2 : -4.2), 0.12, APRON_ROAD_Z),
      new THREE.Vector3(CONC_X[g[0]] + (g[0] === "C" ? -4.2 : 4.2), 0.06, HALL.z0 - 0.5),
    ];
    return toward ? p : p.reverse();
  };
  const pts: THREE.Vector3[] = [];
  if (fromGate) pts.push(...leg(fromGate, true));
  pts.push(hall.clone().add(new THREE.Vector3(-2, 0, 0)), hall.clone().add(new THREE.Vector3(2, 0, 0)));
  if (toGate) pts.push(...leg(toGate, false));
  return pts;
}

export const PRESETS: Record<string, { pos: [number, number, number]; target: [number, number, number] }> = {
  full: { pos: [70, 76, 66], target: [2, 0, -18] },
  A: { pos: [-6, 26, 18], target: [-26, 0, -18] },
  B: { pos: [20, 26, 18], target: [0, 0, -18] },
  C: { pos: [46, 26, 18], target: [26, 0, -20] },
  departures: { pos: [0, 70, -10], target: [0, 0, -19] },
  routes: { pos: [-40, 42, 40], target: [0, 1, -4] },
  ground: { pos: [30, 20, 46], target: [0, 0, 22] },
};
