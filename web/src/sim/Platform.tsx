import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Text } from "@react-three/drei";
import * as THREE from "three";
import { closureActive } from "./pose";
import { useSim } from "../store/sim";

export const LABEL_FONT = "/fonts/NotoSans-SemiBold.woff";       // local: drei <Text> must never reach a CDN (§15)

function hatchTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  g.fillStyle = "#3a1416";
  g.fillRect(0, 0, 64, 64);
  g.strokeStyle = "#E5484D";
  g.lineWidth = 10;
  for (let k = -64; k <= 128; k += 24) { g.beginPath(); g.moveTo(k, 64); g.lineTo(k + 64, 0); g.stroke(); }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(10, 1);
  return tex;
}

/** Box 80 × 0.6 × 4 in --rf-line; hatched red with a pulsing edge only during an active closure. */
export default function Platform({ id, name, z, reduced }: { id: string; name: string; z: number; reduced: boolean }) {
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const edge = useRef<THREE.MeshStandardMaterial>(null);
  const hatch = useMemo(hatchTexture, []);
  const plain = useMemo(() => new THREE.Color("#263038"), []);
  const white = useMemo(() => new THREE.Color("#ffffff"), []);
  useFrame(({ clock }) => {
    const s = useSim.getState();
    const closed = (s.scenario?.disruptions.closures ?? []).some((c) => c.platform_id === id && closureActive(c, s.t));
    if (mat.current) {
      const want = closed ? hatch : null;
      if (mat.current.map !== want) { mat.current.map = want; mat.current.needsUpdate = true; }
      mat.current.color.copy(closed ? white : plain);
    }
    if (edge.current) {
      edge.current.visible = closed;
      edge.current.emissiveIntensity = reduced ? 1 : 0.6 + 0.6 * Math.sin(clock.elapsedTime * 4);
    }
  });
  return (
    <group position={[0, 0, z]}>
      <mesh position={[0, 0.3, 0]}>
        <boxGeometry args={[80, 0.6, 4]} />
        <meshStandardMaterial ref={mat} color="#263038" />
      </mesh>
      <mesh position={[0, 0.62, 2.05]}>
        <boxGeometry args={[80, 0.08, 0.12]} />
        <meshStandardMaterial ref={edge} color="#E5484D" emissive="#E5484D" emissiveIntensity={1} visible={false} />
      </mesh>
      {[-1.9, 1.9].map((dz) => (
        <mesh key={dz} position={[0, 0.05, 3.6 + dz * 0.25]}>
          <boxGeometry args={[280, 0.1, 0.18]} />
          <meshStandardMaterial color="#1A222B" />
        </mesh>
      ))}
      <Text font={LABEL_FONT} position={[-44, 1, 0]} fontSize={1.8} color="#7C8B98" anchorX="right">{name}</Text>
    </group>
  );
}
