import { useEffect } from "react";
import { useSim } from "../store/sim";

/** Advances the sim clock: t += speed × Δt (sim-minutes per real second). Pauses on hidden tabs (§15, §38). */
export default function SimClock() {
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000);
      last = now;
      if (!document.hidden) useSim.getState().tick(dt);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  return null;
}
