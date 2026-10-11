import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError, type ScenarioState } from "../api/client";
import { hhmm, toMin } from "../lib/time";
import { useSim } from "../store/sim";

/** Manual entry (booklet common rules: "manual inputs"): type the station's platforms and the trains, then load them
 *  through the same POST /api/scenario/load {station, timetable} as an upload (§17). The server validates every field;
 *  nothing here decides a platform. */

type TrainType = "SF" | "MEX" | "PAS" | "MEMU" | "GDS";
interface PlatformRow { length: string; loop: string; use: string }
interface TrainRow {
  id: string; name: string; type: TrainType; origin: string; destination: string; direction: "UP" | "DN";
  arr: string; dep: string; platform: string; required: string; allowed: string; stock: string; priority: string;
}
interface Draft { name: string; code: string; minGap: string; maxHold: string; platforms: PlatformRow[]; trains: TrainRow[] }

const TYPES: TrainType[] = ["SF", "MEX", "PAS", "MEMU", "GDS"];
const PRIORITY: Record<TrainType, string> = { SF: "1", MEX: "2", PAS: "3", MEMU: "3", GDS: "4" };

function fromScenario(s: ScenarioState): Draft {
  const st = s.station;
  return {
    name: st.name, code: st.code || st.id, minGap: String(st.min_gap), maxHold: String(st.max_hold),
    platforms: st.platforms.map((p) => ({ length: String(p.length_coaches), loop: String(p.goods_loop_wagons ?? 0), use: p.use ?? "" })),
    trains: s.trains.map((tr) => ({
      id: tr.id, name: tr.name, type: tr.type, origin: tr.origin, destination: tr.destination, direction: tr.direction,
      arr: hhmm(tr.arr), dep: hhmm(tr.dep), platform: tr.platform ?? "", required: tr.required_platform ?? "",
      allowed: (tr.allowed_platforms ?? []).map((p) => p.slice(1)).join(","),
      stock: String((tr.type === "GDS" ? tr.wagons : tr.coaches) ?? ""), priority: String(tr.priority),
    })),
  };
}

const blank = (): Draft => ({
  name: "My station", code: "MYST", minGap: "5", maxHold: "30",
  platforms: [{ length: "24", loop: "0", use: "main line" }, { length: "24", loop: "0", use: "main line" }],
  trains: [],
});

const newTrain = (d: Draft): TrainRow => {
  const last = d.trains[d.trains.length - 1];
  return { id: "", name: "", type: "PAS", origin: last?.origin ?? "", destination: last?.destination ?? "", direction: "UP",
    arr: last?.dep ?? "10:00", dep: "", platform: "", required: "", allowed: "", stock: "", priority: "3" };
};

const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

function toPayload(d: Draft) {
  const code = d.code.trim().toUpperCase();
  const station = {
    id: code, code, name: d.name.trim(), min_gap: num(d.minGap), max_hold: num(d.maxHold),
    platforms: d.platforms.map((p, i) => ({ id: `P${i + 1}`, name: `PF ${i + 1}`, length_coaches: num(p.length),
      goods_loop_wagons: num(p.loop) ?? 0, use: p.use.trim() })),
  };
  const trains = d.trains.map((r) => ({
    id: r.id.trim().toUpperCase(), name: r.name.trim(), type: r.type, origin: r.origin.trim().toUpperCase(),
    destination: r.destination.trim().toUpperCase(), direction: r.direction, arr: r.arr.trim(), dep: r.dep.trim(),
    platform: r.platform || null, required_platform: r.required || null,
    allowed_platforms: r.allowed.split(/[,\s]+/).filter(Boolean).map((x) => `P${x.replace(/^p(f)?/i, "")}`),
    coaches: r.type === "GDS" ? null : num(r.stock) ?? null, wagons: r.type === "GDS" ? num(r.stock) ?? null : null,
    priority: num(r.priority),
  }));
  return { station, timetable: { station: code, day: "Sun", trains } };
}

export default function TimetableEditor() {
  const { t } = useTranslation();
  const scenario = useSim((s) => s.scenario);
  const busy = useSim((s) => s.busy);
  const set = useSim((s) => s.set);
  const setScenario = useSim((s) => s.setScenario);
  const setPlan = useSim((s) => s.setPlan);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [working, setWorking] = useState(false);

  const d = draft;
  const pfIds = d ? d.platforms.map((_, i) => `P${i + 1}`) : [];
  const patch = (u: Partial<Draft>) => setDraft((x) => (x ? { ...x, ...u } : x));
  const setPf = (i: number, u: Partial<PlatformRow>) => d && patch({ platforms: d.platforms.map((p, k) => (k === i ? { ...p, ...u } : p)) });
  const setTr = (i: number, u: Partial<TrainRow>) => d && patch({ trains: d.trains.map((r, k) => (k === i ? { ...r, ...u } : r)) });

  function describe(loc: unknown[], msg: string): string {
    const [head, idx, field] = loc;
    if (head === "trains" && typeof idx === "number") {
      const id = d?.trains[idx]?.id || "—";
      return t("editor.errTrain", { row: idx + 1, id, field: String(field ?? ""), msg });
    }
    if (head === "platforms" && typeof idx === "number") return t("editor.errPlatform", { pf: idx + 1, field: String(field ?? ""), msg });
    return t("editor.errStation", { field: loc.map(String).join("."), msg });
  }

  /** Friendly checks for the usual typing slips; the server still validates every field. */
  function precheck(dr: Draft): string[] {
    const out: string[] = [];
    const row = (i: number, field: string, key: string) =>
      out.push(t("editor.errTrain", { row: i + 1, id: dr.trains[i].id || "—", field: t(field), msg: t(key) }));
    if (!/^[A-Za-z0-9]{2,8}$/.test(dr.code.trim())) out.push(t("editor.errStation", { field: t("editor.stationCode"), msg: t("editor.badStationCode") }));
    const seen = new Set<string>();
    dr.trains.forEach((r, i) => {
      const id = r.id.trim().toUpperCase();
      if (!/^(\d{5}|GDS-\d{4})$/.test(id)) row(i, "field.train", "editor.badId");
      else if (seen.has(id)) row(i, "field.train", "editor.dupId");
      seen.add(id);
      if (!r.name.trim()) row(i, "editor.name", "editor.required");
      for (const [v, f] of [[r.origin, "editor.from"], [r.destination, "editor.to"]] as const)
        if (!/^[A-Za-z]{2,5}$/.test(v.trim())) row(i, f, "editor.badCode");
      const a = toMin(r.arr), b = toMin(r.dep);
      if (a === null) row(i, "editor.arr", "editor.badTime");
      if (b === null) row(i, "editor.dep", "editor.badTime");
      if (a !== null && b !== null && b <= a) row(i, "editor.dep", "editor.depBeforeArr");
      if (!/^\d+$/.test(r.stock.trim())) row(i, "editor.stock", "editor.badStock");
    });
    return out;
  }

  async function load() {
    if (!d) return;
    if (!d.trains.length) { setErrors([t("editor.noTrains")]); return; }
    const pre = precheck(d);
    if (pre.length) { setErrors(pre); return; }
    const p = toPayload(d);
    setWorking(true);
    setErrors([]);
    try {
      const st = await api.loadCustom(p.station, p.timetable, `manual:${p.station.code || "station"}`);
      setScenario(st);
      setPlan(null);
      const rep = await api.validateScheduled();
      set("scheduledReport", rep);
      set("notice", t("editor.loaded", { count: st.trains.length, name: st.station.name }));
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.detail)) {
        setErrors(e.detail.map((x) => (x && typeof x === "object" && "msg" in x
          ? describe(((x as { loc?: unknown[] }).loc ?? []).filter((l) => l !== "body"), String((x as { msg: unknown }).msg))
          : String(x))));
      } else setErrors([e instanceof Error ? e.message : String(e)]);
    } finally {
      setWorking(false);
    }
  }

  function download() {
    if (!d) return;
    const blob = new Blob([JSON.stringify(toPayload(d), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(d.code || "station").toLowerCase()}_timetable.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const cell = "field num h-9 min-h-0 px-2 py-1 text-sm";
  const pfSelect = (v: string, on: (v: string) => void, label: string) => (
    <select className={cell} value={v} aria-label={label} onChange={(e) => on(e.target.value)}>
      <option value="">—</option>
      {pfIds.map((id) => <option key={id} value={id}>{id.slice(1)}</option>)}
    </select>
  );

  return (
    <details className="rounded-lg border border-line p-2" onToggle={(e) => {
      if ((e.target as HTMLDetailsElement).open && !draft) setDraft(scenario ? fromScenario(scenario) : blank());
    }}>
      <summary className="label cursor-pointer select-none">{t("editor.title")}</summary>
      {d && (
        <div className="mt-2 space-y-3">
          <p className="text-xs text-muted">{t("editor.help")}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setDraft(scenario ? fromScenario(scenario) : blank()); setErrors([]); }}>
              {t("editor.fromLoaded")}</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setDraft(blank()); setErrors([]); }}>{t("editor.blank")}</button>
          </div>

          <fieldset className="min-w-0 space-y-2">
            <legend className="label">{t("editor.station")}</legend>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs">{t("editor.stationName")}
                <input className="field mt-1 w-full" value={d.name} maxLength={80} onChange={(e) => patch({ name: e.target.value })} /></label>
              <label className="text-xs">{t("editor.stationCode")}
                <input className="field num mt-1 w-full uppercase" value={d.code} maxLength={8} onChange={(e) => patch({ code: e.target.value })} /></label>
              <label className="text-xs">{t("editor.minGap")}
                <input className="field num mt-1 w-full" inputMode="numeric" value={d.minGap} onChange={(e) => patch({ minGap: e.target.value })} /></label>
              <label className="text-xs">{t("editor.maxHold")}
                <input className="field num mt-1 w-full" inputMode="numeric" value={d.maxHold} onChange={(e) => patch({ maxHold: e.target.value })} /></label>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-max text-sm">
                <thead><tr className="text-left text-xs text-muted">
                  <th className="pr-1">{t("field.platform")}</th><th className="pr-1">{t("editor.length")}</th>
                  <th className="pr-1">{t("editor.loop")}</th><th className="pr-1">{t("editor.use")}</th><th />
                </tr></thead>
                <tbody>
                  {d.platforms.map((p, i) => (
                    <tr key={i}>
                      <td className="num pr-1">{i + 1}</td>
                      <td className="pr-1"><input className={`${cell} w-16`} inputMode="numeric" value={p.length} aria-label={t("editor.length")}
                        onChange={(e) => setPf(i, { length: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-16`} inputMode="numeric" value={p.loop} aria-label={t("editor.loop")}
                        onChange={(e) => setPf(i, { loop: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-40`} value={p.use} maxLength={80} aria-label={t("editor.use")}
                        onChange={(e) => setPf(i, { use: e.target.value })} /></td>
                      <td>{i === d.platforms.length - 1 && d.platforms.length > 1 && (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ platforms: d.platforms.slice(0, -1) })}>
                          {t("action.remove")}</button>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.platforms.length < 20 && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ platforms: [...d.platforms, { length: "24", loop: "0", use: "" }] })}>
                {t("editor.addPlatform")}</button>)}
            <p className="text-xs text-muted">{t("editor.useHelp")}</p>
          </fieldset>

          <fieldset className="min-w-0 space-y-2">
            <legend className="label">{t("editor.trains", { count: d.trains.length })}</legend>
            <div className="max-h-96 overflow-auto">
              <table className="min-w-max text-sm">
                <thead className="sticky top-0 bg-raised"><tr className="text-left text-xs text-muted">
                  {["field.train", "editor.name", "editor.type", "editor.from", "editor.to", "editor.dir", "editor.arr", "editor.dep",
                    "editor.schPf", "editor.reqPf", "editor.allowed", "editor.stock", "editor.priority"].map((k) => (
                    <th key={k} className="whitespace-nowrap pr-1">{t(k)}</th>))}
                  <th />
                </tr></thead>
                <tbody>
                  {d.trains.map((r, i) => (
                    <tr key={i}>
                      <td className="pr-1"><input className={`${cell} w-24`} value={r.id} placeholder="12345" aria-label={t("field.train")}
                        onChange={(e) => setTr(i, { id: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-36 font-sans`} value={r.name} maxLength={60} aria-label={t("editor.name")}
                        onChange={(e) => setTr(i, { name: e.target.value })} /></td>
                      <td className="pr-1"><select className={cell} value={r.type} aria-label={t("editor.type")}
                        onChange={(e) => { const ty = e.target.value as TrainType; setTr(i, { type: ty, priority: PRIORITY[ty] }); }}>
                        {TYPES.map((x) => <option key={x}>{x}</option>)}</select></td>
                      <td className="pr-1"><input className={`${cell} w-16 uppercase`} value={r.origin} maxLength={5} placeholder="ABC"
                        aria-label={t("editor.from")} onChange={(e) => setTr(i, { origin: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-16 uppercase`} value={r.destination} maxLength={5} placeholder="XYZ"
                        aria-label={t("editor.to")} onChange={(e) => setTr(i, { destination: e.target.value })} /></td>
                      <td className="pr-1"><select className={cell} value={r.direction} aria-label={t("editor.dir")}
                        onChange={(e) => setTr(i, { direction: e.target.value as "UP" | "DN" })}><option>UP</option><option>DN</option></select></td>
                      <td className="pr-1"><input className={`${cell} w-16`} value={r.arr} placeholder="HH:MM" aria-label={t("editor.arr")}
                        onChange={(e) => setTr(i, { arr: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-16`} value={r.dep} placeholder="HH:MM" aria-label={t("editor.dep")}
                        onChange={(e) => setTr(i, { dep: e.target.value })} /></td>
                      <td className="pr-1">{pfSelect(r.platform, (v) => setTr(i, { platform: v }), t("editor.schPf"))}</td>
                      <td className="pr-1">{pfSelect(r.required, (v) => setTr(i, { required: v }), t("editor.reqPf"))}</td>
                      <td className="pr-1"><input className={`${cell} w-20`} value={r.allowed} placeholder="1,2" aria-label={t("editor.allowed")}
                        onChange={(e) => setTr(i, { allowed: e.target.value })} /></td>
                      <td className="pr-1"><input className={`${cell} w-14`} inputMode="numeric" value={r.stock} aria-label={t("editor.stock")}
                        onChange={(e) => setTr(i, { stock: e.target.value })} /></td>
                      <td className="pr-1"><select className={cell} value={r.priority} aria-label={t("editor.priority")}
                        onChange={(e) => setTr(i, { priority: e.target.value })}>{["1", "2", "3", "4"].map((x) => <option key={x}>{x}</option>)}</select></td>
                      <td className="whitespace-nowrap">
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ trains: [...d.trains.slice(0, i + 1), { ...r, id: "" }, ...d.trains.slice(i + 1)] })}>
                          {t("editor.copy")}</button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ trains: d.trains.filter((_, k) => k !== i) })}>
                          {t("action.remove")}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.trains.length < 200 && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ trains: [...d.trains, newTrain(d)] })}>{t("editor.addTrain")}</button>)}
            <p className="text-xs text-muted">{t("editor.trainHelp")}</p>
          </fieldset>

          {errors.length > 0 && (
            <ul role="alert" className="max-h-40 space-y-0.5 overflow-auto text-sm text-conflict">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" disabled={working || !!busy} onClick={() => void load()}>
              {working ? t("app.working") : t("editor.load")}</button>
            <button type="button" className="btn btn-ghost" onClick={download}>{t("editor.download")}</button>
          </div>
        </div>
      )}
    </details>
  );
}
