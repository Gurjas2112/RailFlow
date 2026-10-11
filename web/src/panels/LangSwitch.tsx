import { useTranslation } from "react-i18next";
import { changeLang, LANGS, type Lang } from "../i18n";
import { api } from "../api/client";
import { useSim } from "../store/sim";

/** EN · हिं · मर — remembered on the user record when signed in (§14, §37). */
export default function LangSwitch() {
  const { t, i18n } = useTranslation();
  const session = useSim((s) => s.session);
  const cur = (i18n.resolvedLanguage || "en") as Lang;
  return (
    <div role="group" aria-label={t("lang.label")} className="inline-flex overflow-hidden rounded-lg border border-line">
      {LANGS.map((l) => (
        <button key={l} type="button" lang={l} aria-pressed={cur === l}
          onClick={async () => { await changeLang(l); if (session) api.setLang(l).catch(() => undefined); }}
          className={`min-h-9 min-w-11 px-2 text-sm ${cur === l ? "bg-raised text-ink" : "text-muted hover:text-ink"}`}>
          {t(`lang.${l}`)}
        </button>
      ))}
    </div>
  );
}
