import { useTranslation } from "react-i18next";
import { hhmm } from "../lib/time";
import { useSim } from "../store/sim";

/** Time scrubber · which plan is viewed (Applied / A / B / Baseline) · before ⇄ after · 3D/2D/Gantt (§14, §15). */
export default function ViewBar({ allow3d }: { allow3d: boolean }) {
  const { t } = useTranslation();
  const tNow = useSim((s) => Math.round(s.t));
  const scenario = useSim((s) => s.scenario);
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const showBefore = useSim((s) => s.showBefore);
  const stationView = useSim((s) => s.stationView);
  const mainView = useSim((s) => s.mainView);
  const { set, setT } = useSim.getState();
  const times = (scenario?.trains ?? []).flatMap((x) => [x.arr, x.dep]);
  const lo = Math.floor((Math.min(...times, 720) - 30) / 15) * 15;
  const hi = Math.ceil((Math.max(...times, 1020) + 30) / 15) * 15;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex min-w-48 flex-1 items-center gap-2">
        <span className="sr-only">{t("clock.scrub")}</span>
        <span className="num text-xs text-muted">{hhmm(lo)}</span>
        <input type="range" min={lo} max={hi} step={1} value={Math.max(lo, Math.min(hi, tNow))}
          onChange={(e) => setT(Number(e.target.value))} className="h-11 flex-1 accent-[var(--rf-signal)]" aria-valuetext={hhmm(tNow)} />
        <span className="num text-xs text-muted">{hhmm(hi)}</span>
      </label>
      <div role="group" aria-label={t("view.label")} className="flex flex-wrap gap-1">
        <button type="button" aria-pressed={view === "applied"} className={`btn btn-sm ${view === "applied" ? "" : "btn-ghost"}`}
          onClick={() => set("view", "applied")}>{t("view.applied")}</button>
        {plan?.revisions.map((r) => (
          <button key={r.revision.id} type="button" aria-pressed={view === r.revision.id}
            className={`btn btn-sm ${view === r.revision.id ? "" : "btn-ghost"} ${r.validation.valid ? "" : "text-conflict"}`}
            onClick={() => set("view", r.revision.id)}>{t(`methodShort.${r.revision.method}`)}</button>
        ))}
      </div>
      {plan && (
        <button type="button" aria-pressed={showBefore} className={`btn btn-sm ${showBefore ? "" : "btn-ghost"}`}
          onClick={() => set("showBefore", !showBefore)}>{t("view.beforeAfter")}</button>
      )}
      <div role="group" aria-label={t("view.mode")} className="flex gap-1">
        {allow3d && (
          <button type="button" aria-pressed={mainView === "station" && stationView === "3d"}
            className={`btn btn-sm ${mainView === "station" && stationView === "3d" ? "" : "btn-ghost"}`}
            onClick={() => { set("mainView", "station"); set("stationView", "3d"); }}>{t("view.3d")}</button>
        )}
        <button type="button" aria-pressed={mainView === "station" && stationView === "2d"}
          className={`btn btn-sm ${mainView === "station" && stationView === "2d" ? "" : "btn-ghost"}`}
          onClick={() => { set("mainView", "station"); set("stationView", "2d"); }}>{t("view.2d")}</button>
        <button type="button" aria-pressed={mainView === "gantt"} className={`btn btn-sm ${mainView === "gantt" ? "" : "btn-ghost"}`}
          onClick={() => set("mainView", "gantt")}>{t("view.gantt")}</button>
      </div>
    </div>
  );
}
