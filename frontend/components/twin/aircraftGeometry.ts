// Procedural wide-body silhouette (no third-party model, no livery). Nose points to local −Z.
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

let cache: { body: THREE.BufferGeometry; engines: THREE.BufferGeometry; fin: THREE.BufferGeometry; glass: THREE.BufferGeometry } | null = null;

function planform(points: [number, number][], depth: number, y: number) {
  const s = new THREE.Shape();
  points.forEach(([x, z], i) => (i ? s.lineTo(x, z) : s.moveTo(x, z)));
  s.closePath();
  const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.02, bevelSegments: 1 });
  g.rotateX(Math.PI / 2); // shape y → world z, extrusion → −y
  g.translate(0, y + depth, 0);
  return g.toNonIndexed();
}

export function aircraftGeometry() {
  if (cache) return cache;
  const fus = new THREE.CapsuleGeometry(0.27, 3.95, 8, 20);
  fus.rotateX(Math.PI / 2);
  fus.scale(1, 1.04, 1);
  fus.translate(0, 0.58, 0);
  // tail cone taper: squeeze the rear vertices upward a little
  const p = fus.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i);
    if (z > 1.2) {
      const t = Math.min(1, (z - 1.2) / 1.1);
      const y = p.getY(i) - 0.58;
      const x = p.getX(i);
      p.setX(i, x * (1 - 0.55 * t));
      p.setY(i, 0.58 + y * (1 - 0.5 * t) + 0.1 * t);
    }
  }
  fus.computeVertexNormals();
  const wing = planform([[0.0, -0.62], [2.3, 0.42], [2.32, 0.7], [0.0, 0.46], [-2.32, 0.7], [-2.3, 0.42]], 0.05, 0.42);
  const stab = planform([[0.0, 1.72], [0.98, 2.2], [0.99, 2.36], [0.0, 2.26], [-0.99, 2.36], [-0.98, 2.2]], 0.035, 0.72);
  const body = mergeGeometries([fus.toNonIndexed(), wing, stab])!;

  const fs = new THREE.Shape();
  fs.moveTo(1.35, 0); fs.lineTo(2.18, 1.0); fs.lineTo(2.42, 1.0); fs.lineTo(2.34, 0); fs.closePath();
  const fin = new THREE.ExtrudeGeometry(fs, { depth: 0.05, bevelEnabled: false });
  fin.rotateY(-Math.PI / 2);
  fin.translate(0.025, 0.74, 0);

  const eng = (x: number) => {
    const c = new THREE.CylinderGeometry(0.15, 0.13, 0.62, 18, 1, false);
    c.rotateX(Math.PI / 2);
    c.translate(x, 0.33, -0.08);
    const pylon = new THREE.BoxGeometry(0.04, 0.12, 0.34);
    pylon.translate(x, 0.43, 0.0);
    return [c.toNonIndexed(), pylon.toNonIndexed()];
  };
  const engines = mergeGeometries([...eng(0.86), ...eng(-0.86)])!;

  // cockpit windows band
  const glass = new THREE.BoxGeometry(0.34, 0.06, 0.22);
  glass.translate(0, 0.7, -2.16);

  cache = { body, engines, fin, glass };
  return cache;
}
