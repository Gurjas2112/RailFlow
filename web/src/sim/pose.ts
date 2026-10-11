// web/src/sim/pose.ts — SPEC §15. The station view is a pure function of (plan, time).
import type { Assignment } from "../api/client";

export const APPROACH_MIN = 3, EXIT_MIN = 3, TRACK_HALF = 120;
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const easeOut = (k: number) => 1 - (1 - k) ** 3;
const easeIn = (k: number) => k ** 3;

export type Pose = { x: number; phase: "arriving" | "dwelling" | "departing" } | null;

export function trainPose(a: Assignment, t: number, reducedMotion = false): Pose {
  if (a.status !== "ASSIGNED" || a.arr == null || a.dep == null) return null;
  if (t < a.arr - APPROACH_MIN || t > a.dep + EXIT_MIN) return null;
  if (reducedMotion) {                                  // jump between phases instead of easing (§38)
    if (t < a.arr) return { x: -TRACK_HALF / 2, phase: "arriving" };
    if (t <= a.dep) return { x: 0, phase: "dwelling" };
    return { x: TRACK_HALF / 2, phase: "departing" };
  }
  if (t < a.arr) return { x: lerp(-TRACK_HALF, 0, easeOut((t - (a.arr - APPROACH_MIN)) / APPROACH_MIN)), phase: "arriving" };
  if (t <= a.dep) return { x: 0, phase: "dwelling" };
  return { x: lerp(0, TRACK_HALF, easeIn((t - a.dep) / EXIT_MIN)), phase: "departing" };
}

/** Is a closure active at sim time t? Half-open [start, end). */
export const closureActive = (c: { start: number; end: number }, t: number) => c.start <= t && t < c.end;
