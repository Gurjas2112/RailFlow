import { useTranslation } from "react-i18next";
import type { ChangeItem } from "../api/client";
import { hhmm } from "../lib/time";
import { renderPart } from "../lib/reason";
import { useSim, viewedChanges, viewedRevision } from "../store/sim";
import { CLASS_TONE } from "./Changes";

const RULES = ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10"];

/** Class chip, before/after, reason sentence, chain via caused_by, validator checks for this train (§14, §45). */
export default function ReasonCard({ sheet = false }: { sheet?: boolean }) {
  const { t } = useTranslation();
  const selected = useSim((s) => s.selected);
  const scenario = useSim((s) => s.scenario);
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const appliedOut = useSim((s) => s.appliedOut);
  const select = useSim((s) => s.select);
  if (!selected || !scenario) return null;
  const changes = viewedChanges({ plan, view, appliedOut });
  const c = changes.get(selected);
  const train = scenario.trains.find((x) => x.id === selected);
  const ro = viewedRevision({ plan, view });
  const report = ro ? ro.validation : scenario.applied_validation;
  const failed = new Map<string, string>();
  for (const k of report.conflicts) if (k.trains.includes(selected)) failed.set(k.rule, k.code);
  const a = (ro?.revision.assignments ?? scenario.applied).find((x) => x.train_id === selected);

  const chain: string[] = [];
  let cur: ChangeItem | undefined = c;
  const seen = new Set<string>();
  while (cur && !seen.has(cur.train_id) && chain.length < 6) {
    seen.add(cur.train_id);
    chain.unshift(cur.train_id);
    const next = cur.caused_by.find((x) => !x.startsWith("closure:"));
    const closure = cur.caused_by.find((x) => x.startsWith("closure:"));
    if (!next) { if (closure) chain.unshift(closure.replace("closure:", "").replace(":", " ")); break; }
    cur = changes.get(next);
    if (!cur) { chain.unshift(next); break; }
  }

  const body = (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="num text-lg font-semibold">{selected}</span>
        {c && <span className={`chip ${CLASS_TONE[c.cls] ?? ""}`}>{t(`class.${c.cls}`)}{c.hold ? ` ${c.hold}′` : ""}</span>}
        {c?.affected && <span className="chip">{t("reason.affected")}</span>}
        <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => select(null)} aria-label={t("app.close")}>✕</button>
      </div>
      {train && <p className="text-sm text-muted">{train.name} · {t(`type.${train.type}`)} · <span className="num">{train.origin}→{train.destination} {train.direction}</span></p>}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div><span className="label">{t("reason.before")}</span>
          <div className="num">{c?.before ? `${c.before.platform} ${hhmm(c.before.arr)}–${hhmm(c.before.dep)}` : "—"}</div></div>
        <div><span className="label">{t("reason.after")}</span>
          <div className="num">{a?.status === "ASSIGNED" ? `${a.platform} ${hhmm(a.arr)}–${hhmm(a.dep)}` : t("class.UNASSIGNED")}</div></div>
      </div>
      {c && c.parts.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-sm">{c.parts.map((p, i) => <li key={i}>{renderPart(t, p)}</li>)}</ul>
      )}
      {chain.length > 1 && (
        <p className="text-sm"><span className="label">{t("reason.chain")}</span> <span className="num">{chain.join(" → ")}</span></p>
      )}
      <div>
        <span className="label">{t("reason.checks")}</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {RULES.map((r) => (
            <span key={r} className={`chip num ${failed.has(r) ? "border-conflict text-conflict" : "border-valid/40 text-valid"}`}
              title={failed.get(r) ?? t(`rule.${r}`)}>
              {failed.has(r) ? "✗" : "✓"} {r}
            </span>
          ))}
        </div>
      </div>
    </div>
  );

  if (sheet) {
    return (
      <div className="fixed inset-x-0 bottom-0 z-40 max-h-[70vh] overflow-auto rounded-t-2xl border-t border-line bg-panel p-4 shadow-2xl"
        style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom, 0px))" }} role="dialog" aria-label={t("reason.title")}>
        {body}
      </div>
    );
  }
  return <section className="panel p-3" aria-label={t("reason.title")}>{body}</section>;
}
