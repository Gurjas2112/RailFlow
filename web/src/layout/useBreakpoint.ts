import { useEffect, useState } from "react";

export type Breakpoint = "phone" | "tablet" | "desktop";

const query = () => {
  const w = window.innerWidth;
  const landscapePhone = window.innerHeight < 500 && w >= 640;          // phones in landscape get the tablet layout
  return w >= 1280 ? "desktop" : w >= 768 || landscapePhone ? "tablet" : "phone";
};

/** < 768 phone · 768–1279 tablet · ≥ 1280 desktop (§38). */
export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(query);
  useEffect(() => {
    const on = () => setBp(query());
    window.addEventListener("resize", on);
    window.addEventListener("orientationchange", on);
    return () => { window.removeEventListener("resize", on); window.removeEventListener("orientationchange", on); };
  }, []);
  return bp;
}

export function usePrefersReducedMotion(): boolean {
  const [r, setR] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setR(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return r;
}

export function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
