import * as THREE from "three";

let tex: THREE.CanvasTexture | null = null;

/** Procedural apron concrete: slab joints + subtle noise (no external texture files). */
export function concreteTexture() {
  if (tex || typeof document === "undefined") return tex;
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const g = c.getContext("2d")!;
  g.fillStyle = "#1b2230";
  g.fillRect(0, 0, 512, 512);
  const img = g.getImageData(0, 0, 512, 512);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 14;
    img.data[i] += n; img.data[i + 1] += n; img.data[i + 2] += n * 1.1;
  }
  g.putImageData(img, 0, 0);
  g.strokeStyle = "rgba(0,0,0,0.35)";
  g.lineWidth = 2;
  for (let k = 0; k <= 512; k += 128) {
    g.beginPath(); g.moveTo(k, 0); g.lineTo(k, 512); g.stroke();
    g.beginPath(); g.moveTo(0, k); g.lineTo(512, k); g.stroke();
  }
  for (let s = 0; s < 40; s++) {
    g.fillStyle = `rgba(${Math.random() > 0.5 ? 0 : 255},${Math.random() > 0.5 ? 0 : 255},255,0.012)`;
    g.fillRect(Math.random() * 512, Math.random() * 512, 30 + Math.random() * 120, 30 + Math.random() * 120);
  }
  tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(26, 26);
  tex.anisotropy = 8;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export const M = {
  glass: new THREE.MeshPhysicalMaterial({
    color: "#8fb6d8", metalness: 0.2, roughness: 0.06, transparent: true, opacity: 0.26, envMapIntensity: 1.6,
    clearcoat: 1, side: THREE.DoubleSide, depthWrite: false,
  }),
  glassDark: new THREE.MeshPhysicalMaterial({
    color: "#5d7a99", metalness: 0.4, roughness: 0.1, transparent: true, opacity: 0.5, envMapIntensity: 1.4, clearcoat: 1,
  }),
  roof: new THREE.MeshStandardMaterial({ color: "#b4bfcb", metalness: 0.6, roughness: 0.42, envMapIntensity: 1.0, side: THREE.DoubleSide }),
  roofDark: new THREE.MeshStandardMaterial({ color: "#7f8b99", metalness: 0.6, roughness: 0.45 }),
  structure: new THREE.MeshStandardMaterial({ color: "#2c3646", metalness: 0.5, roughness: 0.5 }),
  floor: new THREE.MeshStandardMaterial({ color: "#2a3140", metalness: 0.1, roughness: 0.55 }),
  floorWarm: new THREE.MeshStandardMaterial({ color: "#3a3428", emissive: "#ffcf8a", emissiveIntensity: 0.12, roughness: 0.6 }),
  white: new THREE.MeshPhysicalMaterial({ color: "#eef2f6", metalness: 0.15, roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.2 }),
  metal: new THREE.MeshStandardMaterial({ color: "#8d97a3", metalness: 0.9, roughness: 0.3 }),
  fin: new THREE.MeshPhysicalMaterial({ color: "#20344c", metalness: 0.3, roughness: 0.3, clearcoat: 0.8 }),
  cockpit: new THREE.MeshStandardMaterial({ color: "#0b1320", metalness: 0.9, roughness: 0.1 }),
  bridge: new THREE.MeshStandardMaterial({ color: "#aab4c0", metalness: 0.6, roughness: 0.35 }),
  marking: new THREE.MeshBasicMaterial({ color: "#d9a93c", transparent: true, opacity: 0.55 }),
  markingWhite: new THREE.MeshBasicMaterial({ color: "#c9d3df", transparent: true, opacity: 0.45 }),
  asphalt: new THREE.MeshStandardMaterial({ color: "#11161f", roughness: 0.9 }),
  grass: new THREE.MeshStandardMaterial({ color: "#0d1712", roughness: 1 }),
  conveyor: new THREE.MeshStandardMaterial({ color: "#3a4352", metalness: 0.7, roughness: 0.4 }),
};
