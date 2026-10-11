import { useTranslation } from "react-i18next";
import { api, type RevisionOut } from "../api/client";
import { renderConflict, renderExplain } from "../lib/reason";
import { hhmm } from "../lib/time";
import { useSim } from "../store/sim";
import { RecoveryBadge, ValidatorBadge } from "./Badges";

/** Revisions side by side: validator verdict, recovery, metrics, explanation, Apply (§14, §47.6). */
export default function Compare() {
  const { t, i18n } = useTranslation();
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const explanation = useSim((s) => s.explanation);
  const appliedId = useSim((s) => s.scenario?.applied_revision_id);
  const trainsTotal = useSim((s) => s.scenario?.trains.length ?? 0);
  const busy = useSim((s) => s.busy);
  const isController = useSim((s) => s.session?.role === "controller");
  const { set, run, setApplied } = useSim.getState();
  const explaining = !explanation && !!plan;
  const dis = useSim.getState().scenario?.disruptions;
  const summary = [
    ...(dis?.delays ?? []).map((d) => `${d.train_id} ${t(`kind.${d.kind}`)} +${d.minutes}′`),
    ...(dis?.closures ?? []).map((c) => `${c.platform_id} ${t("gantt.closed")} ${hhmm(c.start)}–${hhmm(c.end)}`),
  ];

  if (!plan) {
    return (
      <section className="panel p-3" aria-labelledby="cmp-h">
        <h2 id="cmp-h" className="label">{t("panel.compare")}</h2>
        <p className="mt-2 text-sm text-muted">{t("compare.empty")}</p>
      </section>
    );
  }
  const lang = (i18n.resolvedLanguage || "en") as "en" | "hi" | "mr";
  const text = explanation
    ? (explanation.explainer_path === "template" || lang !== "en") && explanation.parts.length
      ? renderExplain(t, explanation.parts) : explanation.text
    : null;

  async function apply(ro: RevisionOut) {
    const st = await run("apply", () => api.apply(ro.revision.id));
    if (st) { setApplied(ro.revision.id, st); set("notice", t("compare.applied", { label: t(`method.${ro.revision.method}`) })); }
  }

  async function reExplain() {
    const ex = await run("explain", () => api.explain(plan!.revisions.slice(0, 2).map((r) => r.revision.id), lang));
    if (ex) set("explanation", ex);
  }

  const rows: { key: string; get: (r: RevisionOut) => React.ReactNode }[] = [
    { key: "compare.totalHold", get: (r) => r.metrics.total_hold_min },
    { key: "compare.weighted", get: (r) => r.metrics.weighted_delay },
    { key: "compare.changes", get: (r) => r.metrics.platform_changes },
    { key: "compare.unassigned", get: (r) => r.metrics.unassigned },
    { key: "compare.affected", get: (r) => r.revision.affected.length ? `${r.metrics.trains_affected} / ${trainsTotal}` : "—" },
    { key: "compare.outside", get: (r) => r.metrics.moved_outside_affected },
    { key: "compare.solver", get: (r) => r.revision.solver_status },
    { key: "compare.solveMs", get: (r) => `${r.revision.solve_ms}` },
  ];

  return (
    <section className="panel space-y-3 p-3" aria-labelledby="cmp-h">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="cmp-h" className="label">{t("panel.compare")}</h2>
        <span className="chip num">{t("compare.now")} {summary.length ? summary.join(" · ") : t("compare.noDisruptions")}</span>
      </div>
      {plan.agree && <p className="rounded-md bg-raised px-2 py-1 text-sm">{t("compare.agree", { count: plan.revisions.length })}</p>}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <thead>
            <tr>
              <th className="w-40" />
              {plan.revisions.map((r) => (
                <th key={r.revision.id} className="px-2 pb-2 text-left align-top">
                  <button type="button" onClick={() => set("view", r.revision.id)} aria-pressed={view === r.revision.id}
                    className={`w-full rounded-md border px-2 py-1 text-left ${view === r.revision.id ? "border-signal" : "border-line"}`}>
                    <div className="font-semibold">{t(`method.${r.revision.method}`)}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <ValidatorBadge report={r.validation} compact />
                      <RecoveryBadge ro={r} />
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.revision.widened && <span className="chip border-held/60 text-held">{t("compare.widened")}</span>}
                      {r.revision.fault_injected && <span className="chip border-conflict text-conflict">{t("compare.fault")}</span>}
                      {appliedId === r.revision.id && <span className="chip border-signal text-ink">{t("compare.isApplied")}</span>}
                    </div>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t border-line">
                <th scope="row" className="py-1.5 pr-2 text-left font-normal text-muted">{t(row.key)}</th>
                {plan.revisions.map((r) => <td key={r.revision.id} className="num px-2 py-1.5">{row.get(r)}</td>)}
              </tr>
            ))}
            <tr className="border-t border-line align-top">
              <th />
              {plan.revisions.map((r) => (
                <td key={r.revision.id} className="px-2 py-2">
                  {!r.validation.valid && (
                    <ul className="mb-2 space-y-1">
                      {r.validation.conflicts.map((c, i) => (
                        <li key={i} className="rounded border-l-4 border-conflict bg-raised px-1.5 py-1 text-xs num">{renderConflict(t, c)}</li>
                      ))}
                    </ul>
                  )}
                  {r.metrics.unassigned > 0 && (
                    <p className="mb-1 text-xs text-unassigned num">
                      {t("compare.unassignedList", { list: r.revision.assignments.filter((a) => a.status !== "ASSIGNED").map((a) => a.train_id).join(", ") })}
                    </p>
                  )}
                  {isController && (
                    <button type="button" className="btn btn-sm w-full"
                      disabled={!r.validation.valid || r.revision.fault_injected || !!busy || appliedId === r.revision.id}
                      onClick={() => void apply(r)}>
                      {r.recovery === "PARTIAL"
                        ? t("action.applyPartial", { count: r.metrics.unassigned })
                        : t("action.apply", { label: r.label })}
                    </button>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {!text && explaining && <p className="text-sm text-muted">{t("compare.explaining")}</p>}
      {text && (
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label">{t("compare.explanation")}</span>
            <span className="chip">{t("chip.explainer")} <span className="num text-ink">{explanation!.explainer_path}</span></span>
            <span className={`chip ${explanation!.grounding === "passed" ? "" : "border-held/60 text-held"}`}>
              {t("chip.grounding")} <span className="num text-ink">{explanation!.grounding}</span>
            </span>
            {isController && <button type="button" className="btn btn-ghost btn-sm" onClick={() => void reExplain()}>{t("action.explainAgain")}</button>}
          </div>
          <p className="text-sm">{text}</p>
        </div>
      )}
    </section>
  );
}
