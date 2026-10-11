import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import Header from "../panels/Header";
import Audit from "../panels/Audit";
import Changes from "../panels/Changes";
import Compare from "../panels/Compare";
import Disruption from "../panels/Disruption";
import ReasonCard from "../panels/ReasonCard";
import ScenarioPanel from "../panels/ScenarioPanel";
import StationArea from "../panels/StationArea";
import SimClock from "../sim/SimClock";
import { useSim } from "../store/sim";
import { hasWebGL, useBreakpoint } from "./useBreakpoint";

/** One codebase, three arrangements (§14, §38). Controller actions appear only for controllers. */
export default function Workspace() {
  const bp = useBreakpoint();
  const role = useSim((s) => s.session?.role);
  const scenario = useSim((s) => s.scenario);
  const notice = useSim((s) => s.notice);
  const set = useSim((s) => s.set);
  const webgl = useMemo(hasWebGL, []);
  const { t } = useTranslation();

  useEffect(() => { api.scenario().then((s) => useSim.getState().setScenario(s)).catch(() => undefined); }, []);
  useEffect(() => { if (bp === "phone" || !webgl) set("stationView", "2d"); }, [bp, webgl, set]);
  useKeyboard(bp === "desktop");

  if (!scenario) return (<><Header compact={bp === "phone"} /><div className="p-6 text-muted">{t("app.loading")}</div></>);
  const controller = role === "controller";
  return (
    <div className="min-h-full">
      <SimClock />
      <Header compact={bp === "phone"} />
      {notice && (
        <div className="mx-3 mt-2 flex items-center justify-between gap-2 rounded-md border border-line bg-panel px-3 py-1.5 text-sm" role="status">
          <span>{notice}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => set("notice", null)}>{t("app.dismiss")}</button>
        </div>
      )}
      {bp === "desktop" ? <DesktopLayout controller={controller} webgl={webgl} />
        : bp === "tablet" ? <TabletLayout controller={controller} webgl={webgl} />
          : <PhoneLayout controller={controller} webgl={webgl} />}
    </div>
  );
}

function DesktopLayout({ controller, webgl }: { controller: boolean; webgl: boolean }) {
  return (
    <div className="grid grid-cols-[minmax(340px,400px)_1fr] gap-3 p-3">
      <aside className="space-y-3">
        {controller && <Disruption />}
        <ScenarioPanel />
        <Audit />
      </aside>
      <main className="min-w-0 space-y-3">
        <StationArea height={440} allow3d={webgl} lowPower={false} />
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
          <div className="min-w-0 space-y-3"><Compare /><Changes /></div>
          <div className="w-0 empty:hidden [&:has(section)]:w-[380px]"><div className="sticky top-24"><ReasonCard /></div></div>
        </div>
      </main>
    </div>
  );
}

function TabletLayout({ controller, webgl }: { controller: boolean; webgl: boolean }) {
  const [open, setOpen] = useState(true);
  const { t } = useTranslation();
  return (
    <div className={`grid gap-3 p-3 ${open ? "grid-cols-[minmax(300px,360px)_1fr]" : "grid-cols-[auto_1fr]"}`}>
      <aside className="space-y-3">
        <button type="button" className="btn btn-ghost btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? t("layout.collapse") : t("layout.expand")}
        </button>
        {open && (<>{controller && <Disruption />}<Compare /><ScenarioPanel /></>)}
      </aside>
      <main className="min-w-0 space-y-3">
        <StationArea height={380} allow3d={webgl} lowPower={false} />
        <ReasonCard />
        <Changes />
      </main>
    </div>
  );
}

type Tab = "station" | "disrupt" | "compare" | "changes";

function PhoneLayout({ controller, webgl }: { controller: boolean; webgl: boolean }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("station");
  const tabs: Tab[] = controller ? ["station", "disrupt", "compare", "changes"] : ["station", "changes"];
  return (
    <div className="pb-24">
      <main className="space-y-3 p-3">
        {tab === "station" && <StationArea height={320} allow3d={webgl} lowPower />}
        {tab === "disrupt" && controller && (<><Disruption /><ScenarioPanel /></>)}
        {tab === "compare" && controller && <Compare />}
        {tab === "changes" && <Changes />}
        {!controller && tab === "station" && <ScenarioPanel />}
      </main>
      <ReasonCard sheet />
      <nav className="fixed inset-x-0 bottom-0 z-30 grid border-t border-line bg-void/95 backdrop-blur"
        style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))`, paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
        aria-label={t("nav.tabs")}>
        {tabs.map((k) => (
          <button key={k} type="button" aria-current={tab === k ? "page" : undefined} onClick={() => setTab(k)}
            className={`min-h-14 text-sm ${tab === k ? "text-ink" : "text-muted"}`}>
            <span className={`mx-auto mb-1 block h-0.5 w-8 rounded ${tab === k ? "bg-signal" : "bg-transparent"}`} />
            {t(`tab.${k}`)}
          </button>
        ))}
      </nav>
    </div>
  );
}

/** Space play/pause · ←/→ ±5 min · V 3D/2D · B before/after · 1/2/3 Applied/A/B (desktop only, §14). */
function useKeyboard(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const on = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      const s = useSim.getState();
      if (e.key === " ") { e.preventDefault(); s.set("playing", !s.playing); }
      else if (e.key === "ArrowLeft") s.setT(s.t - 5);
      else if (e.key === "ArrowRight") s.setT(s.t + 5);
      else if (e.key === "v" || e.key === "V") { s.set("mainView", "station"); s.set("stationView", s.stationView === "3d" ? "2d" : "3d"); }
      else if (e.key === "b" || e.key === "B") s.set("showBefore", !s.showBefore);
      else if (e.key === "1") s.set("view", "applied");
      else if (e.key === "2" && s.plan?.revisions[0]) s.set("view", s.plan.revisions[0].revision.id);
      else if (e.key === "3" && s.plan?.revisions[1]) s.set("view", s.plan.revisions[1].revision.id);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [enabled]);
}
