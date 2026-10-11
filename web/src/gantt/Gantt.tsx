// web/src/gantt/Gantt.tsx — the 2D truth view (SPEC §16). Plain SVG, no library.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Assignment, ChangeItem } from "../api/client";
import { hhmm } from "../lib/time";
import { renderParts } from "../lib/reason";
import {
  delayTags, STATE_VAR, trainState, useSim, viewedAssignments, viewedChanges, viewedConflictTrains, viewedRevision,
} from "../store/sim";

const ROW = 52, HEAD = 28, LABEL_W = 64, BAR_H = 30;

export default function Gantt({ pxPerMin = 4 }: { pxPerMin?: number }) {
  const { t } = useTranslation();
  const scenario = useSim((s) => s.scenario);
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const appliedOut = useSim((s) => s.appliedOut);
  const showBefore = useSim((s) => s.showBefore);
  const selected = useSim((s) => s.selected);
  const select = useSim((s) => s.select);
  const setT = useSim((s) => s.setT);
  const now = useSim((s) => Math.floor(s.t));
  const scroller = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ a: Assignment; x: number; y: number } | null>(null);
  const dragging = useRef(false);

  const st = { view, plan, scenario, appliedOut };
  const assignments = viewedAssignments(st);
  const changes = viewedChanges(st);
  const conflicts = viewedConflictTrains(st);
  const delays = delayTags(st);
  const ro = viewedRevision(st);
  const report = ro ? ro.validation : scenario?.applied_validation;
  const platforms = scenario?.station.platforms ?? [];
  const gap = scenario?.station.min_gap ?? 5;
  const closures = scenario?.disruptions.closures ?? [];

  const [t0, t1] = useMemo(() => {
    const times = (scenario?.trains ?? []).flatMap((x) => [x.arr, x.dep]);
    const lo = Math.min(...times, scenario?.now ?? 720) - 15;
    const hi = Math.max(...times.map((v) => v + 60), (scenario?.now ?? 720) + 60) + 15;
    return [Math.floor(lo / 15) * 15, Math.ceil(hi / 15) * 15];
  }, [scenario]);
  const W = (t1 - t0) * pxPerMin;
  const rows = [...platforms.map((p) => p.id), "UNASSIGNED"];
  const H = HEAD + rows.length * ROW;
  const x = (m: number) => (m - t0) * pxPerMin;
  const y = (pid: string | null | undefined) => HEAD + Math.max(0, rows.indexOf(pid ?? "UNASSIGNED")) * ROW + (ROW - BAR_H) / 2;

  useEffect(() => {                                  // open centred on "now"
    const el = scroller.current;
    if (el) el.scrollLeft = Math.max(0, x(scenario?.now ?? t0) - el.clientWidth / 2 + LABEL_W);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.scenario_id, pxPerMin]);

  const byId = new Map(assignments.map((a) => [a.train_id, a]));
  const unassigned = assignments.filter((a) => a.status !== "ASSIGNED");

  function timeAt(clientX: number, svg: SVGSVGElement) {
    const r = svg.getBoundingClientRect();
    return t0 + (clientX - r.left) / pxPerMin;
  }

  const gridLines = [];
  for (let m = t0; m <= t1; m += 15) gridLines.push(m);

  const connectors: { from: Assignment; to: Assignment; label?: string; kind: "conflict" | "cause" }[] = [];
  for (const c of report?.conflicts ?? []) {
    if (c.trains.length === 2 && (c.code === "OVERLAP" || c.code === "GAP_VIOLATION")) {
      const a = byId.get(c.trains[0]), b = byId.get(c.trains[1]);
      if (a && b) connectors.push({ from: a, to: b, kind: "conflict",
        label: c.code === "OVERLAP" ? `${c.stay_overlap_min}′/${c.reserved_overlap_min}′` : `−${c.clearance_shortfall_min}′` });
    }
  }
  for (const ch of changes.values()) {
    for (const cb of ch.caused_by ?? []) {
      const from = byId.get(cb), to = byId.get(ch.train_id);
      if (from && to && from.platform && to.platform) connectors.push({ from, to, kind: "cause" });
    }
  }

  return (
    <div className="relative">
      <div ref={scroller} className="overflow-x-auto overscroll-x-contain rounded-lg border border-line bg-panel" aria-label={t("gantt.label")}>
        <div className="flex" style={{ width: LABEL_W + W }}>
          <div className="sticky left-0 z-10 shrink-0 border-r border-line bg-panel" style={{ width: LABEL_W }}>
            <div style={{ height: HEAD }} />
            {rows.map((r) => (
              <div key={r} className="flex items-center px-2 text-sm font-semibold" style={{ height: ROW }}>
                {r === "UNASSIGNED" ? <span className="text-xs text-unassigned">{t("gantt.unassigned")}</span>
                  : <span className="num">{platforms.find((p) => p.id === r)?.name ?? r}</span>}
              </div>
            ))}
          </div>
          <svg width={W} height={H} role="img" aria-label={t("gantt.label")} className="block touch-pan-x select-none"
            onPointerDown={(e) => {
              const tm = timeAt(e.clientX, e.currentTarget);
              if (Math.abs(tm - now) * pxPerMin < 14 || e.clientY - e.currentTarget.getBoundingClientRect().top < HEAD) {
                dragging.current = true;
                e.currentTarget.setPointerCapture(e.pointerId);
                setT(tm);
              }
            }}
            onPointerMove={(e) => { if (dragging.current) setT(timeAt(e.clientX, e.currentTarget)); }}
            onPointerUp={() => { dragging.current = false; }}>
            <defs>
              <pattern id="rf-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="8" height="8" fill="transparent" />
                <line x1="0" y1="0" x2="0" y2="8" stroke="var(--st-closed)" strokeWidth="3" />
              </pattern>
            </defs>
            {rows.map((r, i) => (
              <rect key={r} x={0} y={HEAD + i * ROW} width={W} height={ROW} fill={i % 2 ? "transparent" : "rgba(255,255,255,0.015)"} />
            ))}
            {gridLines.map((m) => (
              <g key={m}>
                <line x1={x(m)} x2={x(m)} y1={HEAD - 6} y2={H} stroke="var(--rf-line)" strokeWidth={m % 60 === 0 ? 1.2 : 0.6} />
                {m % 30 === 0 && <text x={x(m) + 3} y={16} fill="var(--rf-muted)" fontSize={11} className="num">{hhmm(m)}</text>}
              </g>
            ))}
            {closures.map((c, i) => (
              <g key={i}>
                <rect x={x(c.start)} y={y(c.platform_id) - 6} width={(c.end - c.start) * pxPerMin} height={BAR_H + 12}
                  fill="url(#rf-hatch)" stroke="var(--st-closed)" strokeWidth={1} opacity={0.75} />
                <text x={x(c.start) + 4} y={y(c.platform_id) - 9} fill="var(--st-closed)" fontSize={10} className="num">
                  {t("gantt.closed")} {hhmm(c.start)}–{hhmm(c.end)}
                </text>
              </g>
            ))}
            {showBefore && [...changes.values()].filter((c) => c.before && c.before.platform !== c.after.platform || (c.before && c.before.arr !== c.after.arr))
              .map((c) => c.before && c.before.arr != null && c.before.dep != null ? (
                <rect key={`g${c.train_id}`} x={x(c.before.arr)} y={y(c.before.platform)} width={(c.before.dep - c.before.arr) * pxPerMin}
                  height={BAR_H} rx={4} fill="var(--rf-muted)" opacity={0.3} strokeDasharray="4 3" stroke="var(--rf-muted)" />
              ) : null)}
            {assignments.filter((a) => a.status === "ASSIGNED" && a.arr != null && a.dep != null).map((a) => {
              const change = changes.get(a.train_id);
              const state = trainState(a, change, conflicts, delays.has(a.train_id), now);
              const fill = STATE_VAR[state];
              const bx = x(a.arr!), bw = Math.max(3, (a.dep! - a.arr!) * pxPerMin), by = y(a.platform);
              const isSel = selected === a.train_id;
              return (
                <g key={a.train_id} className="cursor-pointer" onClick={() => select(a.train_id)}
                  onPointerEnter={(e) => setHover({ a, x: e.clientX, y: e.clientY })} onPointerLeave={() => setHover(null)}>
                  <rect x={bx + bw} y={by + 6} width={gap * pxPerMin} height={BAR_H - 12} fill={fill} opacity={0.28} />
                  <rect x={bx} y={by} width={bw} height={BAR_H} rx={4} fill={fill} opacity={state === "frozen" ? 0.55 : 0.92}
                    stroke={conflicts.has(a.train_id) ? "var(--st-conflict)" : isSel ? "var(--rf-text)" : "transparent"}
                    strokeWidth={conflicts.has(a.train_id) ? 3 : 2} />
                  <text x={bx + 4} y={by + BAR_H / 2 + 4} fontSize={11} fill="#071016" className="num" pointerEvents="none">{a.train_id}</text>
                  {delays.has(a.train_id) && (
                    <text x={bx} y={by - 3} fontSize={10} fill="var(--st-delayed)" className="num">+{delays.get(a.train_id)}′</text>
                  )}
                </g>
              );
            })}
            {unassigned.map((a, i) => {
              const tr = scenario?.trains.find((x2) => x2.id === a.train_id);
              const bx = x(tr?.arr ?? t0) + (i % 2) * 2;
              return (
                <g key={`u${a.train_id}`} className="cursor-pointer" onClick={() => select(a.train_id)}>
                  <rect x={bx} y={y("UNASSIGNED")} width={Math.max(3, ((tr?.dep ?? 0) - (tr?.arr ?? 0)) * pxPerMin)} height={BAR_H} rx={4}
                    fill="none" stroke="var(--st-unassigned)" strokeDasharray="5 3" strokeWidth={2} />
                  <text x={bx + 4} y={y("UNASSIGNED") + BAR_H / 2 + 4} fontSize={11} fill="var(--st-unassigned)" className="num">{a.train_id}</text>
                </g>
              );
            })}
            {connectors.map((c, i) => {
              const ax = x(c.from.dep ?? 0), ay = y(c.from.platform) + BAR_H / 2;
              const bx = x(c.to.arr ?? 0), by = y(c.to.platform) + BAR_H / 2;
              return c.kind === "conflict" ? (
                <g key={i}>
                  <line x1={ax} y1={ay} x2={bx} y2={by} stroke="var(--st-conflict)" strokeWidth={2} />
                  <text x={(ax + bx) / 2 + 3} y={Math.min(ay, by) - 4} fill="var(--st-conflict)" fontSize={11} className="num">{c.label}</text>
                </g>
              ) : (
                <path key={i} d={`M${ax},${ay} C${ax + 20},${ay} ${bx - 20},${by} ${bx},${by}`} fill="none"
                  stroke="var(--rf-muted)" strokeWidth={1} strokeDasharray="2 3" markerEnd="" />
              );
            })}
            <g pointerEvents="none">
              <line x1={x(now)} x2={x(now)} y1={HEAD - 8} y2={H} stroke="var(--rf-signal)" strokeWidth={2} />
              <rect x={x(now) - 22} y={2} width={44} height={18} rx={4} fill="var(--rf-signal)" />
              <text x={x(now)} y={15} textAnchor="middle" fontSize={11} fill="#031417" className="num">{hhmm(now)}</text>
            </g>
          </svg>
        </div>
      </div>
      {hover && <Tooltip a={hover.a} change={changes.get(hover.a.train_id)} px={hover.x} py={hover.y} />}
    </div>
  );
}

function Tooltip({ a, change, px, py }: { a: Assignment; change?: ChangeItem; px: number; py: number }) {
  const { t } = useTranslation();
  return (
    <div className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-line bg-raised p-2 text-xs shadow-xl"
      style={{ left: Math.min(px + 12, window.innerWidth - 300), top: py + 12 }}>
      <div className="num font-semibold">{a.train_id} · {a.platform} · {hhmm(a.arr)}–{hhmm(a.dep)}</div>
      {change && <div className="mt-1 text-muted">{t(`class.${change.cls}`)} — {renderParts(t, change.parts)}</div>}
    </div>
  );
}
