import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Billboard, RoundedBox, Text } from "@react-three/drei";
import * as THREE from "three";
import type { Assignment } from "../api/client";
import { trainPose } from "./pose";
import { LABEL_FONT } from "./Platform";
import {
  delayTags, STATE_HEX, trainState, useSim, viewedChanges, viewedConflictTrains,
} from "../store/sim";

interface Props { a: Assignment; zOf: (pid: string) => number; reduced: boolean; lowPower: boolean }

/** RoundedBox 36 × 2.4 × 2.6 coloured by state; pose from (plan, t) every frame, never from React state (§15). */
export default function Train({ a, zOf, reduced, lowPower }: Props) {
  const ref = useRef<THREE.Group>(null!);
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const label = useRef<THREE.Group>(null);
  // Delay tag is a troika Text mesh, not drei <Html>: each <Html> owns a separate React root, and remounting
  // 30 trains on a view change unmounted those roots mid-render (React 19 removeChild crash).
  const tag = useRef<THREE.Mesh & { text: string; sync: () => void }>(null);
  const tagText = useRef("");
  const color = useRef(new THREE.Color());
  useFrame(({ clock }) => {
    const s = useSim.getState();
    const p = trainPose(a, s.t, reduced);
    ref.current.visible = !!p && !!a.platform;
    if (!p || !a.platform) return;
    ref.current.position.set(p.x, 1.9, zOf(a.platform) + 3.6);
    const st = { view: s.view, plan: s.plan, scenario: s.scenario, appliedOut: s.appliedOut };
    const conflicts = viewedConflictTrains(st);
    const delays = delayTags(st);
    const state = trainState(a, viewedChanges(st).get(a.train_id), conflicts, delays.has(a.train_id), s.t);
    if (mat.current) {
      color.current.set(STATE_HEX[state]);
      mat.current.color.copy(color.current);
      const pulse = state === "conflict" ? (reduced ? 0.6 : 0.4 + 0.4 * Math.sin(clock.elapsedTime * 6)) : 0;
      mat.current.emissive.set(state === "conflict" ? "#E5484D" : "#000000");
      mat.current.emissiveIntensity = pulse;
    }
    if (label.current) label.current.visible = !lowPower || s.selected === a.train_id || conflicts.has(a.train_id);
    if (tag.current) {
      const d = delays.get(a.train_id);
      const txt = d ? `+${d}m` : "";
      tag.current.visible = !!d;
      if (txt !== tagText.current) { tagText.current = txt; tag.current.text = txt; tag.current.sync(); }
    }
  });
  return (
    <group ref={ref} visible={false} onClick={(e) => { e.stopPropagation(); useSim.getState().select(a.train_id); }}>
      <RoundedBox args={[36, 2.4, 2.6]} radius={0.6} smoothness={lowPower ? 2 : 4}>
        <meshStandardMaterial ref={mat} color="#2BB673" />
      </RoundedBox>
      <group ref={label}>
        <Billboard position={[0, 3, 0]}>
          <Text font={LABEL_FONT} fontSize={1.6} color="#E6EDF2" outlineWidth={0.08} outlineColor="#0B0F14">{a.train_id}</Text>
        </Billboard>
      </group>
      <Billboard position={[15, 3.2, 0]}>
        <Text ref={tag} visible={false} font={LABEL_FONT} fontSize={1.5} color={STATE_HEX.delayed}
          outlineWidth={0.1} outlineColor="#0B0F14">{""}</Text>
      </Billboard>
    </group>
  );
}
