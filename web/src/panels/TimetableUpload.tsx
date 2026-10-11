import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type UploadResponse } from "../api/client";
import { useSim } from "../store/sim";

/** .xlsx / .csv / .json → pick a sheet if several qualify → load → Check as scheduled (§40). */
export default function TimetableUpload() {
  const { t } = useTranslation();
  const run = useSim((s) => s.run);
  const setScenario = useSim((s) => s.setScenario);
  const set = useSim((s) => s.set);
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<UploadResponse | null>(null);

  async function send(f: File, sheet?: string) {
    const r = await run("upload", () => api.upload(f, sheet));
    if (!r) return;
    setRes(r);
    if (r.timetable && r.station) {
      const state = await run("load", () => api.loadCustom(r.station, r.timetable,
        `upload:${f.name}${r.sheet ? ` · ${r.sheet}` : ""}`));
      if (state) {
        setScenario(state);
        const rep = await run("check", () => api.validateScheduled());
        if (rep) set("scheduledReport", rep);
        set("notice", t("upload.loaded", { count: state.trains.length, sheet: r.sheet ?? f.name }) +
          (state.station.id !== "SVNJ"
            ? ` · ${t("upload.station", { name: state.station.name, count: state.station.platforms.length })}` : ""));
      }
    }
  }

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="label">{t("upload.label")}</span>
        <input type="file" accept=".xlsx,.csv,.json" className="mt-1 block w-full text-sm file:mr-2 file:min-h-11 file:rounded-lg file:border file:border-line file:bg-raised file:px-3 file:text-ink"
          onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); setRes(null); if (f) void send(f); }} />
      </label>
      <p className="text-xs text-muted">{t("upload.help")}</p>
      <p className="flex flex-wrap gap-x-3 text-xs">
        <a className="underline" href="/templates/railflow_template.xlsx" download>{t("upload.templateXlsx")}</a>
        <a className="underline" href="/templates/railflow_template.json" download>{t("upload.templateJson")}</a>
      </p>
      {res?.needs_sheet && file && (
        <div className="space-y-1">
          <p className="text-sm">{t("upload.pickSheet")}</p>
          <div className="flex flex-wrap gap-2">
            {res.needs_sheet.map((s) => (
              <button key={s} type="button" className="btn btn-ghost btn-sm" onClick={() => void send(file, s)}>{s}</button>
            ))}
          </div>
        </div>
      )}
      {res?.errors && (
        <ul role="alert" className="max-h-40 space-y-0.5 overflow-auto text-sm text-conflict">
          {res.errors.map((e, i) => <li key={i} className="num">{e}</li>)}
        </ul>
      )}
      {res?.excluded && res.excluded.length > 0 && (
        <p className="text-xs text-muted">{t("upload.excluded", { list: res.excluded.join("; ") })}</p>
      )}
    </div>
  );
}
