import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Confirmed, type Proposal } from "../api/client";
import { hhmm, toMin } from "../lib/time";
import { renderProposalReason } from "../lib/reason";
import { useSim } from "../store/sim";
import RadioInput from "./RadioInput";

type Draft = Proposal & { edited?: boolean };

/** Free text → proposals with source spans → edit / remove → Confirm & plan (§5, §10.1, §14). */
export default function Disruption() {
  const { t, i18n } = useTranslation();
  const scenario = useSim((s) => s.scenario);
  const text = useSim((s) => s.draftText);
  const planNow = useSim((s) => s.planNow);
  const parserPath = useSim((s) => s.parserPath);
  const fault = useSim((s) => s.injectFault);
  const busy = useSim((s) => s.busy);
  const { set, run, setPlan, refresh } = useSim.getState();
  const [items, setItems] = useState<Draft[]>([]);
  const [unparsed, setUnparsed] = useState<string[]>([]);
  const [parsedText, setParsedText] = useState("");
  const [path, setPath] = useState<"llm" | "regex" | "manual">("manual");

  const trainIds = useMemo(() => new Set((scenario?.trains ?? []).map((x) => x.id)), [scenario]);
  const platformIds = (scenario?.station.platforms ?? []).map((p) => p.id);
  const nowOk = toMin(planNow) !== null;

  async function parse() {
    const r = await run("parse", () => api.parse(text, planNow));
    if (!r) return;
    setItems([...r.proposals, ...r.rejected]);
    setUnparsed(r.unparsed);
    setParsedText(text);
    setPath(r.parser_path);
    set("parserPath", r.parser_path);
  }

  function check(p: Draft): Draft {
    // Client-side re-check after an edit; the server checks again on /api/plan (never trusted).
    if (p.type === "delay") {
      const ok = !!p.train_id && trainIds.has(p.train_id) && !!p.minutes && p.minutes >= 1 && p.minutes <= 600;
      return { ...p, edited: true, status: ok ? "ok" : "needs_clarification", reason: ok ? null : p.reason };
    }
    const s = toMin(p.start ?? ""), e = toMin(p.end ?? "");
    const ok = !!p.platform_id && platformIds.includes(p.platform_id) && s !== null && e !== null && s < e;
    return { ...p, edited: true, status: ok ? "ok" : "needs_clarification", reason: ok ? null : p.reason };
  }

  const update = (id: string, patch: Partial<Draft>) => setItems((xs) => xs.map((x) => (x.id === id ? check({ ...x, ...patch }) : x)));
  const remove = (id: string) => setItems((xs) => xs.filter((x) => x.id !== id));
  const add = (type: "delay" | "closure") => setItems((xs) => [...xs, check({
    id: `m${Date.now()}`, type, status: "needs_clarification", source: "", span: null, ambiguous: false,
    ...(type === "delay" ? { train_id: "", minutes: 10, kind: "arrival" } : { platform_id: platformIds[0], start: planNow, end: planNow }),
  } as Draft)]);

  const blocked = items.length === 0 || items.some((p) => p.status !== "ok") || !nowOk;

  async function confirm() {
    const confirmed: Confirmed[] = items.map((p) => p.type === "delay"
      ? { type: "delay", train_id: p.train_id!, minutes: p.minutes!, kind: p.kind ?? "arrival", source: p.source || null }
      : { type: "closure", platform_id: p.platform_id!, start: p.start!, end: p.end!, source: p.source || null });
    const manual = items.some((p) => p.edited) || path === "manual";
    const plan = await run("plan", () => api.plan(confirmed, planNow, fault, parsedText || text, manual ? "manual" : path));
    if (!plan) return;
    setPlan(plan);
    setItems([]);
    await refresh();
    // The explanation never blocks the controller: the plan is usable while the local model writes.
    const ids = plan.revisions.slice(0, 2).map((r) => r.revision.id);
    api.explain(ids, (i18n.resolvedLanguage || "en") as "en" | "hi" | "mr")
      .then((ex) => { if (useSim.getState().plan?.revisions[0]?.revision.id === ids[0]) set("explanation", ex); })
      .catch(() => undefined);
  }

  return (
    <section className="panel space-y-3 p-3" aria-labelledby="dis-h">
      <div className="flex items-center justify-between gap-2">
        <h2 id="dis-h" className="label">{t("panel.disruption")}</h2>
        {parserPath && <span className={`chip ${parserPath === "regex" ? "border-held/60 text-held" : ""}`}>{t("chip.parser")} <span className="num text-ink">{parserPath}</span></span>}
      </div>
      <RadioInput />
      <label className="block">
        <span className="sr-only">{t("disruption.textLabel")}</span>
        <textarea className="field min-h-28 resize-y" maxLength={1000} value={text} placeholder={t("disruption.placeholder")}
          onChange={(e) => set("draftText", e.target.value)} />
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="w-28">
          <span className="label">{t("disruption.now")}</span>
          <input className={`field num ${nowOk ? "" : "border-conflict"}`} value={planNow} inputMode="numeric" pattern="\d{2}:\d{2}"
            onChange={(e) => set("planNow", e.target.value)} aria-invalid={!nowOk} />
        </label>
        <button type="button" className="btn" disabled={!text.trim() || !!busy || !nowOk} onClick={() => void parse()}>
          {busy === "parse" ? t("app.working") : t("action.parse")}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => add("delay")}>{t("disruption.addDelay")}</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => add("closure")}>{t("disruption.addClosure")}</button>
      </div>

      {parsedText && items.some((p) => p.span) && <Highlighted text={parsedText} items={items} />}

      {items.length > 0 && (
        <ul className="space-y-2" aria-live="polite">
          {items.map((p) => <ProposalRow key={p.id} p={p} platforms={platformIds} onChange={update} onRemove={remove} />)}
        </ul>
      )}
      {unparsed.length > 0 && (
        <div className="text-xs text-muted">
          <span className="label">{t("disruption.unparsed")}</span>
          <ul className="mt-1 list-disc pl-5">{unparsed.map((u, i) => <li key={i}>{u}</li>)}</ul>
        </div>
      )}
      {items.length > 0 && (
        <button type="button" className="btn w-full" disabled={blocked || !!busy} onClick={() => void confirm()}>
          {busy === "plan" ? t("app.working") : t("action.confirmPlan")}
        </button>
      )}
      {items.length > 0 && blocked && <p className="text-xs text-held">{t("disruption.blocked")}</p>}

      {scenario && (scenario.disruptions.delays.length > 0 || scenario.disruptions.closures.length > 0) && (
        <div>
          <span className="label">{t("disruption.confirmed")}</span>
          <ul className="mt-1 space-y-0.5 text-sm">
            {scenario.disruptions.delays.map((d, i) => (
              <li key={`d${i}`} className="num">{d.train_id} {t(`kind.${d.kind}`)} +{d.minutes}′</li>
            ))}
            {scenario.disruptions.closures.map((c, i) => (
              <li key={`c${i}`} className="num">{c.platform_id} {t("gantt.closed")} {hhmm(c.start)}–{hhmm(c.end)}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Highlighted({ text, items }: { text: string; items: Draft[] }) {
  const { t } = useTranslation();
  const spans = items.filter((p) => p.span).map((p) => ({ s: p.span![0], e: p.span![1], bad: p.status === "rejected" }))
    .sort((a, b) => a.s - b.s);
  const out: React.ReactNode[] = [];
  let pos = 0;
  spans.forEach((sp, i) => {
    if (sp.s < pos) return;
    out.push(text.slice(pos, sp.s));
    out.push(<mark key={i} className={sp.bad ? "rounded bg-conflict/25 text-ink" : "mark"}>{text.slice(sp.s, sp.e)}</mark>);
    pos = sp.e;
  });
  out.push(text.slice(pos));
  return <p className="rounded-lg border border-line bg-void p-2 text-sm" aria-label={t("disruption.spans")}>{out}</p>;
}

function ProposalRow({ p, platforms, onChange, onRemove }: {
  p: Draft; platforms: string[]; onChange: (id: string, patch: Partial<Draft>) => void; onRemove: (id: string) => void;
}) {
  const { t } = useTranslation();
  const tone = p.status === "ok" ? "border-valid/50" : p.status === "rejected" ? "border-conflict" : "border-held";
  return (
    <li className={`rounded-lg border-l-4 ${tone} bg-raised p-2`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip">{t(`proposalType.${p.type}`)}</span>
        <span className={`text-xs ${p.status === "ok" ? "text-valid" : p.status === "rejected" ? "text-conflict" : "text-held"}`}>
          {t(`proposalStatus.${p.status}`)}
        </span>
        <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => onRemove(p.id)} aria-label={t("action.remove")}>✕</button>
      </div>
      {p.type === "delay" ? (
        <div className="mt-2 grid grid-cols-3 gap-2">
          <input className="field num" aria-label={t("field.train")} value={p.train_id ?? p.train_ref ?? ""}
            onChange={(e) => onChange(p.id, { train_id: e.target.value.trim().toUpperCase() })} />
          <input className="field num" aria-label={t("field.minutes")} type="number" min={1} max={600} value={p.minutes ?? ""}
            onChange={(e) => onChange(p.id, { minutes: Number(e.target.value) })} />
          <select className="field" aria-label={t("field.kind")} value={p.kind ?? "arrival"}
            onChange={(e) => onChange(p.id, { kind: e.target.value as "arrival" | "departure" })}>
            <option value="arrival">{t("kind.arrival")}</option>
            <option value="departure">{t("kind.departure")}</option>
          </select>
        </div>
      ) : (
        <div className="mt-2 grid grid-cols-3 gap-2">
          <select className="field num" aria-label={t("field.platform")} value={p.platform_id ?? ""}
            onChange={(e) => onChange(p.id, { platform_id: e.target.value })}>
            <option value="">—</option>
            {platforms.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
          <input className="field num" aria-label={t("field.start")} value={p.start ?? ""} onChange={(e) => onChange(p.id, { start: e.target.value })} />
          <input className="field num" aria-label={t("field.end")} value={p.end ?? ""} onChange={(e) => onChange(p.id, { end: e.target.value })} />
        </div>
      )}
      {p.status !== "ok" && (p.reason || p.message) && (
        <p className="mt-1 text-xs text-held">{renderProposalReason(t, p.reason, p.message)}</p>
      )}
    </li>
  );
}
