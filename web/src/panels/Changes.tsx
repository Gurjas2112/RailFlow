import { useTranslation } from "react-i18next";
import type { ChangeItem } from "../api/client";
import { hhmm } from "../lib/time";
import { renderParts } from "../lib/reason";
import { useSim, viewedChanges } from "../store/sim";

export const CLASS_TONE: Record<string, string> = {
  MOVED: "text-moved border-moved/60", MOVED_HELD: "text-moved border-moved/60", HELD: "text-held border-held/60",
  DELAYED: "text-delayed border-delayed/60", UNASSIGNED: "text-unassigned border-unassigned", FROZEN: "text-muted border-line",
  UNCHANGED: "text-ontime border-ontime/50",
};

const changed = (c: ChangeItem) => c.cls !== "UNCHANGED" && !(c.cls === "FROZEN" && c.before?.dep === c.after.dep);

/** Every train that differs from the applied plan, with its reason; click → reason card (§11, §14). */
export default function Changes() {
  const { t } = useTranslation();
  const plan = useSim((s) => s.plan);
  const view = useSim((s) => s.view);
  const appliedOut = useSim((s) => s.appliedOut);
  const selected = useSim((s) => s.selected);
  const select = useSim((s) => s.select);
  const list = [...viewedChanges({ plan, view, appliedOut }).values()].filter(changed)
    .sort((a, b) => (a.after.arr ?? 9999) - (b.after.arr ?? 9999));

  return (
    <section className="panel p-3" aria-labelledby="chg-h">
      <h2 id="chg-h" className="label">{t("panel.changes", { count: list.length })}</h2>
      {list.length === 0 ? <p className="mt-2 text-sm text-muted">{t("changes.none")}</p> : (
        <ul className="mt-2 divide-y divide-line">
          {list.map((c) => (
            <li key={c.train_id}>
              <button type="button" onClick={() => select(c.train_id)} aria-pressed={selected === c.train_id}
                className={`flex min-h-11 w-full flex-wrap items-center gap-x-3 gap-y-1 py-2 text-left ${selected === c.train_id ? "bg-raised" : ""}`}>
                <span className="num w-20 font-semibold">{c.train_id}</span>
                <span className={`chip ${CLASS_TONE[c.cls] ?? ""}`}>{t(`class.${c.cls}`)}</span>
                <span className="num text-sm">
                  {c.before?.platform ?? "—"} {hhmm(c.before?.arr)} → {c.after.platform ?? "—"} {hhmm(c.after.arr)}
                  {c.hold > 0 && <span className="text-held"> +{c.hold}′</span>}
                </span>
                <span className="w-full text-xs text-muted">{renderParts(t, c.parts)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
