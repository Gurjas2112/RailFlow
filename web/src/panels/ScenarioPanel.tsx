import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { hhmm } from "../lib/time";
import { renderConflict } from "../lib/reason";
import { useSim } from "../store/sim";
import TimetableUpload from "./TimetableUpload";

/** Built-in scenarios, Check as scheduled, Assign platforms, Reset, Inject planner fault (§14, §22). */
export default function ScenarioPanel() {
  const { t } = useTranslation();
  const scenarios = useSim((s) => s.scenarios);
  const scenario = useSim((s) => s.scenario);
  const report = useSim((s) => s.scheduledReport);
  const planNow = useSim((s) => s.planNow);
  const fault = useSim((s) => s.injectFault);
  const busy = useSim((s) => s.busy);
  const isController = useSim((s) => s.session?.role === "controller");
  const { run, set, setScenario, setPlan, setScenarios } = useSim.getState();

  useEffect(() => { api.scenarios().then(setScenarios).catch(() => undefined); }, [setScenarios]);

  async function load(id: string) {
    const st = await run("load", () => api.load(id));
    if (!st) return;
    setScenario(st);
    const sc = scenarios.find((s) => s.id === id);
    set("draftText", sc?.text ?? "");
    set("injectFault", !!sc?.inject_fault);
    set("parserPath", null);
    set("notice", sc?.expect ? t("scenario.expect", { text: t(`scenarioExpect.${sc.id}`, { defaultValue: sc.expect }) }) : null);
  }

  return (
    <section className="panel space-y-3 p-3" aria-labelledby="sc-h">
      <div className="flex items-center justify-between gap-2">
        <h2 id="sc-h" className="label">{t("panel.scenario")}</h2>
        {scenario && <span className="chip num" title={scenario.scenario_id}>{scenario.source}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {scenarios.map((s) => (
          <button key={s.id} type="button" disabled={!isController || !!busy} title={t(`scenarioName.${s.id}`, { defaultValue: s.name })}
            aria-pressed={scenario?.source === s.id}
            className={`btn btn-sm ${scenario?.source === s.id ? "" : "btn-ghost"}`} onClick={() => void load(s.id)}>
            <span className="num">{s.id}</span>
          </button>
        ))}
      </div>
      {scenario && (
        <p className="text-xs text-muted">
          {t(`scenarioName.${scenario.source}`, { defaultValue: scenarios.find((s) => s.id === scenario.source)?.name ?? scenario.source })}
          {" · "}{t("scenario.trains", { count: scenario.trains.length })}{" · "}{t("scenario.now")} <span className="num">{hhmm(scenario.now)}</span>
        </p>
      )}
      {isController && (
        <>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-ghost" disabled={!!busy}
              onClick={async () => { const r = await run("check", () => api.validateScheduled()); if (r) set("scheduledReport", r); }}>
              {t("action.checkScheduled")}
            </button>
            <button type="button" className="btn btn-ghost" disabled={!!busy}
              onClick={async () => { const p = await run("assign", () => api.assign(planNow)); if (p) setPlan(p); }}>
              {busy === "assign" ? t("app.working") : t("action.assign")}
            </button>
            <button type="button" className="btn btn-ghost" disabled={!!busy}
              onClick={async () => { const st = await run("reset", () => api.reset()); if (st) { setScenario(st); setPlan(null); } }}>
              {t("action.reset")}
            </button>
          </div>
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-5 w-5 accent-[var(--st-conflict)]" checked={fault}
              onChange={(e) => set("injectFault", e.target.checked)} />
            {t("action.injectFault")}
          </label>
          <TimetableUpload />
        </>
      )}
      {report && (
        <div className="space-y-1" aria-live="polite">
          <div className={`text-sm font-semibold ${report.valid ? "text-valid" : "text-invalid"}`}>
            {report.valid ? t("scheduled.none") : t("scheduled.found", { count: report.conflicts.length })}
          </div>
          <ul className="space-y-1">
            {report.conflicts.map((c, i) => (
              <li key={i} className="rounded border-l-4 border-conflict bg-raised px-2 py-1 text-sm">
                <span className="num">{renderConflict(t, c)}</span>
                <div className="text-xs text-muted">{t(`conflictDesc.${c.code}`)}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
