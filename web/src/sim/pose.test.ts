import { describe, expect, it } from "vitest";
import { APPROACH_MIN, EXIT_MIN, TRACK_HALF, closureActive, trainPose } from "./pose";
import type { Assignment } from "../api/client";

const a: Assignment = { train_id: "11209", status: "ASSIGNED", platform: "P4", arr: 885, dep: 895, hold: 13, reason_code: null };

describe("trainPose — the view is a pure function of (plan, t)", () => {
  it("is absent outside the approach/exit window", () => {
    expect(trainPose(a, a.arr! - APPROACH_MIN - 0.01)).toBeNull();
    expect(trainPose(a, a.dep! + EXIT_MIN + 0.01)).toBeNull();
  });
  it("arrives from the west, dwells at x = 0, departs east", () => {
    expect(trainPose(a, a.arr! - APPROACH_MIN)).toEqual({ x: -TRACK_HALF, phase: "arriving" });
    expect(trainPose(a, a.arr!)).toEqual({ x: 0, phase: "dwelling" });
    expect(trainPose(a, a.dep!)).toEqual({ x: 0, phase: "dwelling" });
    expect(trainPose(a, a.dep! + EXIT_MIN)).toEqual({ x: TRACK_HALF, phase: "departing" });
  });
  it("is monotonic while arriving", () => {
    const xs = [0, 0.5, 1, 1.5, 2, 2.5].map((k) => trainPose(a, a.arr! - APPROACH_MIN + k)!.x);
    for (let i = 1; i < xs.length; i++) expect(xs[i]).toBeGreaterThan(xs[i - 1]);
  });
  it("never draws an unassigned train", () => {
    expect(trainPose({ ...a, status: "UNASSIGNED", platform: null }, 890)).toBeNull();
  });
  it("jumps between phases under reduced motion", () => {
    expect(trainPose(a, a.arr! - 1, true)!.phase).toBe("arriving");
    expect(trainPose(a, a.dep! + 1, true)!.x).toBe(TRACK_HALF / 2);
  });
  it("treats closures as half-open [start, end)", () => {
    expect(closureActive({ start: 840, end: 930 }, 840)).toBe(true);
    expect(closureActive({ start: 840, end: 930 }, 930)).toBe(false);
  });
});
