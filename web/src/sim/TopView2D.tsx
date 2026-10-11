// web/src/sim/TopView2D.tsx — the 2D top view (§15 hard-cut fallback, phone default). Same trainPose() as the 3D view.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { closureActive, TRACK_HALF, trainPose } from "./pose";
import {
  delayTags, STATE_HEX, trainState, useSim, viewedAssignments, viewedChanges, viewedConflictTrains,
} from "../store/sim";
import { usePrefersReducedMotion } from "../layout/useBreakpoint";

export default function TopView2D({ height = 320 }: { height?: number }) {
  const { t } = useTranslation();
  const canvas = useRef<HTMLCanvasElement>(null);
  const reduced = usePrefersReducedMotion();
  const hits = useRef<{ id: string; x: number; y: number; w: number; h: number }[]>([]);
  const select = useSim((s) => s.select);

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const c = canvas.current;
      if (!c || document.hidden) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
      const g = c.getContext("2d");
      if (!g) return;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const s = useSim.getState();
      const plats = s.scenario?.station.platforms ?? [];
      const now = s.t;
      g.fillStyle = "#0B0F14";
      g.fillRect(0, 0, w, h);
      const lane = (h - 20) / Math.max(1, plats.length);
      const left = 56, right = w - 12, mid = (left + right) / 2;
      const sx = (x: number) => mid + (x / TRACK_HALF) * ((right - left) / 2);
      const pfW = (right - left) * 0.42;
      const yOf = new Map<string, number>();
      plats.forEach((p, i) => {
        const y = 10 + i * lane + lane / 2;
        yOf.set(p.id, y);
        g.fillStyle = "#1A222B";
        g.fillRect(left, y - 1, right - left, 2);                          // track
        const closed = (s.scenario?.disruptions.closures ?? []).some((c) => c.platform_id === p.id && closureActive(c, now));
        g.fillStyle = "#263038";
        g.fillRect(mid - pfW / 2, y + lane * 0.18, pfW, lane * 0.16);      // platform edge
        if (closed) {
          g.save();
          g.beginPath();
          g.rect(mid - pfW / 2, y - lane * 0.3, pfW, lane * 0.64);
          g.clip();
          g.strokeStyle = "#E5484D";
          g.lineWidth = 3;
          for (let k = -lane; k < pfW + lane; k += 9) {
            g.beginPath();
            g.moveTo(mid - pfW / 2 + k, y + lane * 0.34);
            g.lineTo(mid - pfW / 2 + k + lane * 0.64, y - lane * 0.3);
            g.stroke();
          }
          g.restore();
          g.strokeStyle = "#E5484D";
          g.strokeRect(mid - pfW / 2, y - lane * 0.3, pfW, lane * 0.64);
        }
        g.fillStyle = "#7C8B98";
        g.font = "600 12px 'JetBrains Mono', monospace";
        g.fillText(p.name, 6, y + 4);
      });
      const st = { view: s.view, plan: s.plan, scenario: s.scenario, appliedOut: s.appliedOut };
      const changes = viewedChanges(st), conflicts = viewedConflictTrains(st), delays = delayTags(st);
      hits.current = [];
      const tw = pfW * 0.85, th = Math.min(22, lane * 0.42);
      for (const a of viewedAssignments(st)) {
        const pose = trainPose(a, now, reduced);
        if (!pose || !a.platform) continue;
        const y = yOf.get(a.platform);
        if (y === undefined) continue;
        const state = trainState(a, changes.get(a.train_id), conflicts, delays.has(a.train_id), now);
        const x = sx(pose.x) - tw / 2;
        g.globalAlpha = state === "conflict" && !reduced ? 0.65 + 0.35 * Math.sin(performance.now() / 160) : 1;
        g.fillStyle = STATE_HEX[state];
        g.beginPath();
        g.roundRect(x, y - th / 2, tw, th, 6);
        g.fill();
        g.globalAlpha = 1;
        if (s.selected === a.train_id) { g.strokeStyle = "#E6EDF2"; g.lineWidth = 2; g.stroke(); }
        g.fillStyle = "#071016";
        g.font = "600 12px 'JetBrains Mono', monospace";
        g.fillText(a.train_id, x + 6, y + 4);
        if (delays.has(a.train_id)) {
          g.fillStyle = "#F2A33A";
          g.fillText(`+${delays.get(a.train_id)}m`, x + tw - 34, y - th / 2 - 3);
        }
        hits.current.push({ id: a.train_id, x, y: y - th / 2, w: tw, h: th });
      }
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);

  return (
    <canvas ref={canvas} role="img" aria-label={t("station.topView")} className="block w-full rounded-lg border border-line"
      style={{ height }}
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const px = e.clientX - r.left, py = e.clientY - r.top;
        const hit = hits.current.find((b) => px >= b.x && px <= b.x + b.w && py >= b.y - 8 && py <= b.y + b.h + 8);
        select(hit ? hit.id : null);
      }} />
  );
}
