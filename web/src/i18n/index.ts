// i18next with locale files served from /locales (bundled in the build, works offline — §37, §39).
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

export const LANGS = ["en", "hi", "mr"] as const;
export type Lang = (typeof LANGS)[number];

async function bundle(lng: Lang): Promise<Record<string, string>> {
  const r = await fetch(`/locales/${lng}.json`, { cache: "force-cache" });
  if (!r.ok) throw new Error(`locale ${lng} missing`);
  return r.json();
}

function setHtmlLang(lng: string) {
  document.documentElement.lang = (LANGS as readonly string[]).includes(lng) ? lng : "en";
}

export async function initI18n(): Promise<void> {
  const en = await bundle("en");
  await i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: { en: { translation: en } },
      fallbackLng: "en",
      supportedLngs: [...LANGS],
      nonExplicitSupportedLngs: true,
      keySeparator: false,
      nsSeparator: false,
      interpolation: { escapeValue: false },
      detection: { order: ["localStorage", "navigator"], caches: ["localStorage"], lookupLocalStorage: "rf.lang" },
      returnNull: false,
    });
  const cur = (i18n.resolvedLanguage || "en") as Lang;
  if (cur !== "en") await ensureLang(cur);
  setHtmlLang(cur);
  i18n.on("languageChanged", setHtmlLang);
}

export async function ensureLang(lng: Lang): Promise<void> {
  if (!i18n.hasResourceBundle(lng, "translation")) {
    i18n.addResourceBundle(lng, "translation", await bundle(lng), true, true);
  }
}

export async function changeLang(lng: Lang): Promise<void> {
  await ensureLang(lng);
  await i18n.changeLanguage(lng);
}

export default i18n;
