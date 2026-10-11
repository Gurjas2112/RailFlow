import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { signOut } from "../auth/useSession";
import { hhmm } from "../lib/time";
import { useSim, viewedRevision, type Speed } from "../store/sim";
import { PathChip, ValidatorBadge } from "./Badges";
import LangSwitch from "./LangSwitch";

/** Name · now · play controls · validator badge · status chips · language · identity (§14). */
export default function Header({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const s = useSim();
  const ro = viewedRevision(s);
  const report = ro ? ro.validation : s.scenario?.applied_validation;
  const h = s.health;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-void/95 backdrop-blur"
      style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2">
        <div className="mr-auto min-w-0">
          <div className="font-semibold">{t("app.name")}</div>
          {!compact && (
            <div className="truncate text-xs text-muted">
              {s.scenario && s.scenario.station.id !== "SVNJ"
                ? t("app.stationCustom", { name: s.scenario.station.name, code: s.scenario.station.id })
                : t("app.station")}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2" aria-label={t("clock.label")}>
          <span className="label">{t("clock.now")}</span>
          <span className="num text-lg">{hhmm(s.t)}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => s.set("playing", !s.playing)}
            aria-label={s.playing ? t("clock.pause") : t("clock.play")}>{s.playing ? "❚❚" : "▶"}</button>
          {!compact && ([1, 10, 60] as Speed[]).map((v) => (
            <button key={v} type="button" aria-pressed={s.speed === v}
              className={`btn btn-sm ${s.speed === v ? "" : "btn-ghost"}`} onClick={() => s.set("speed", v)}>
              <span className="num">{v}×</span>
            </button>
          ))}
        </div>

        <ValidatorBadge report={report} compact={compact} />

        {!compact && (
          <div className="flex flex-wrap items-center gap-1.5">
            <PathChip label={t("chip.parser")} value={s.parserPath ?? "—"} warn={s.parserPath === "regex"} />
            <PathChip label={t("chip.explainer")} value={s.explanation?.explainer_path ?? "—"}
              warn={s.explanation?.explainer_path === "template"} />
            <PathChip label={t("chip.ollama")} value={h ? t(`chip.${h.ollama}`) : "—"} warn={h?.ollama !== "up"} />
            {h && h.db !== "ok" && <PathChip label={t("chip.db")} value={h.db} warn />}
          </div>
        )}

        <LangSwitch />

        {s.session && (
          <div className="flex items-center gap-2">
            <span className="text-sm">{s.session.user}</span>
            <span className="chip border-signal/50 text-ink">{t(`role.${s.session.role}`)}</span>
            {s.session.role === "admin" && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/admin")}>{t("nav.admin")}</button>
            )}
            <button type="button" className="btn btn-ghost btn-sm" onClick={async () => { await signOut(); navigate("/login"); }}>
              {t("auth.signOut")}
            </button>
          </div>
        )}
      </div>
      {s.plan?.fault_injected && (
        <div role="alert" className="bg-conflict px-3 py-1.5 text-center text-sm font-semibold text-white">{t("fault.banner")}</div>
      )}
      {s.error && (
        <div role="alert" className="flex items-center justify-between gap-2 bg-raised px-3 py-1.5 text-sm text-conflict">
          <span>{s.error}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => s.set("error", null)}>{t("app.dismiss")}</button>
        </div>
      )}
    </header>
  );
}
