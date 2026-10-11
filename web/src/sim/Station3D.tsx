// web/src/sim/Station3D.tsx — R3F station (SPEC §15). Low-poly and abstract: legibility, not realism.
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { configureTextBuilder } from "troika-three-text";
import { useTranslation } from "react-i18next";
import Platform from "./Platform";
import Train from "./Train";
import { useSim, viewedAssignments } from "../store/sim";
import { usePrefersReducedMotion } from "../layout/useBreakpoint";

// Typeset labels on the main thread: troika's blob-URL workers would need script-src blob:, and the CSP stays default-src 'self' (§33).
configureTextBuilder({ useWorker: false, defaultFontURL: "/fonts/NotoSans-SemiBold.woff", unicodeFontsURL: "/fonts/unicode" });

const HOME: [number, number, number] = [-70, 70, 95];

export default function Station3D({ height = 420, lowPower = false }: { height?: number; lowPower?: boolean }) {
  const { t } = useTranslation();
  const scenario = useSim((s) => s.scenario);
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const assignments = viewedAssignments({ view, plan, scenario });
  const reduced = usePrefersReducedMotion();
  const controls = useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const [hidden, setHidden] = useState(document.hidden);
  const platforms = scenario?.station.platforms ?? [];
  const zOf = useMemo(() => {
    const m = new Map(platforms.map((p, i) => [p.id, (i - (platforms.length - 1) / 2) * 8]));
    return (pid: string) => m.get(pid) ?? 0;
  }, [platforms]);

  useEffect(() => {
    const vis = () => setHidden(document.hidden);
    const key = (e: KeyboardEvent) => {
      if ((e.key === "r" || e.key === "R") && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        controls.current?.reset();
      }
    };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("keydown", key);
    return () => { document.removeEventListener("visibilitychange", vis); window.removeEventListener("keydown", key); };
  }, []);

  return (
    <div className="relative overflow-hidden rounded-lg border border-line" style={{ height }} role="img" aria-label={t("station.view3d")}>
      <Canvas camera={{ position: HOME, fov: 40, near: 1, far: 1200 }} dpr={lowPower ? [1, 1.5] : [1, 2]}
        gl={{ antialias: !lowPower, powerPreference: "high-performance" }} frameloop={hidden ? "never" : "always"}
        onPointerMissed={() => useSim.getState().select(null)}>
        <color attach="background" args={["#0B0F14"]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[40, 80, 40]} intensity={1.1} />
        {platforms.map((p) => <Platform key={p.id} id={p.id} name={p.name} z={zOf(p.id)} reduced={reduced} />)}
        {assignments.filter((a) => a.status === "ASSIGNED").map((a) => (
          <Train key={`${view}-${a.train_id}`} a={a} zOf={zOf} reduced={reduced} lowPower={lowPower} />
        ))}
        <OrbitControls ref={controls} makeDefault target={[0, 0, 0]} enablePan={false} minDistance={40} maxDistance={260}
          minPolarAngle={0.25} maxPolarAngle={1.35} />
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-2 text-xs text-muted">{t("station.cameraHint")}</div>
    </div>
  );
}
