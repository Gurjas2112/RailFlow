import { Suspense, lazy } from "react";
import { useTranslation } from "react-i18next";
import Gantt from "../gantt/Gantt";
import TopView2D from "../sim/TopView2D";
import { useSim } from "../store/sim";
import ViewBar from "./ViewBar";

const Station3D = lazy(() => import("../sim/Station3D"));

/** 3D station, 2D top view or Gantt — all rendering the viewed plan at the sim clock. */
export default function StationArea({ height, allow3d, lowPower }: { height: number; allow3d: boolean; lowPower: boolean }) {
  const { t } = useTranslation();
  const stationView = useSim((s) => s.stationView);
  const mainView = useSim((s) => s.mainView);
  const use3d = allow3d && stationView === "3d";
  return (
    <section className="space-y-2" aria-label={t("panel.station")}>
      <ViewBar allow3d={allow3d} />
      {mainView === "gantt" ? <Gantt pxPerMin={lowPower ? 3 : 4} /> : use3d ? (
        <Suspense fallback={<div className="grid place-items-center rounded-lg border border-line text-muted" style={{ height }}>{t("app.loading")}</div>}>
          <Station3D height={height} lowPower={lowPower} />
        </Suspense>
      ) : <TopView2D height={Math.min(height, 360)} />}
      <Legend />
    </section>
  );
}

function Legend() {
  const { t } = useTranslation();
  const items: [string, string][] = [["ontime", "var(--st-ontime)"], ["delayed", "var(--st-delayed)"], ["held", "var(--st-held)"],
    ["moved", "var(--st-moved)"], ["unassigned", "var(--st-unassigned)"], ["conflict", "var(--st-conflict)"], ["frozen", "var(--st-frozen)"]];
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
      {items.map(([k, c]) => (
        <span key={k} className="inline-flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm" style={{ background: c }} />{t(`state.${k}`)}</span>
      ))}
      <span className="inline-flex items-center gap-1"><span className="hatch-closed h-2.5 w-4 rounded-sm" />{t("state.closed")}</span>
    </div>
  );
}
