"use client";
import { useGLTF } from "@react-three/drei";

/** Renders an approved, licensed GLB terminal shell when the backend geometry source provides one
 *  (SKYASSIST_TWIN_GLB). Gates, stands and routes keep coming from the routing graph. */
export default function ApprovedGLB({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}
