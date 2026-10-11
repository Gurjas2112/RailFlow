import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type AdminMetrics } from "../api/client";
import { hhmm } from "../lib/time";

const WINDOWS = [15, 60, 24 * 60];
const AXIS = { stroke: "#7C8B98", fontSize: 11 };
const TIP = { contentStyle: { background: "#1A222B", border: "1px solid #263038", color: "#E6EDF2" } };

/** Operations & System Health — six panels, polled every 5 s (§34). Chrome neutral; state colours only for state. */
export default function Dashboard() {
  const { t } = useTranslation();
  const [win, setWin] = useState(60);
  const [m, setM] = useState<AdminMetrics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const poll = () => api.metrics(win).then((x) => { if (alive) { setM(x); setErr(null); } }).catch((e) => alive && setErr(String(e)));
    poll();
    const id = window.setInterval(poll, 5000);
    return () => { alive = false; window.clearInterval(id); };
  }, [win]);

  if (!m) return <p className="text-muted">{err ?? t("app.loading")}</p>;
  const h = m.health;
  const share = Object.entries(m.ai.parser_share).map(([k, v]) => ({ name: k, value: v }));
  const rules = Object.entries(m.validation.by_rule).map(([k, v]) => ({ name: k, n: v }));
  const status = Object.entries(m.planning.status).map(([k, v]) => ({ name: k, n: v }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-lg font-semibold">{t("admin.title")}</h1>
        <span className="label">{t("admin.window")}</span>
        {WINDOWS.map((w) => (
          <button key={w} type="button" aria-pressed={win === w} className={`btn btn-sm ${win === w ? "" : "btn-ghost"}`}
            onClick={() => setWin(w)}>{t(`admin.win.${w}`)}</button>
        ))}
        <span className="chip">⟳ 5 s</span>
      </div>

      {m.alerts.length > 0 && (
        <div className="flex flex-wrap gap-2" role="alert">
          {m.alerts.map((a) => <span key={a} className="rounded-md bg-conflict px-2 py-1 text-sm font-semibold text-white">{t(`alert.${a}`)}</span>)}
        </div>
      )}

      {/* 1 · system health */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Tile title={t("admin.api")} ok value={t("admin.up")} sub={h.api_p95_ms != null ? `p95 ${h.api_p95_ms} ms` : "—"} />
        <Tile title={t("chip.ollama")} ok={h.ollama === "up"} value={t(`chip.${h.ollama}`)} sub={m.ai.parse_p50_ms != null ? `p50 ${m.ai.parse_p50_ms} ms` : h.model} />
        <Tile title={t("chip.db")} ok={h.db === "ok"} value={h.db} sub={`${(h.db_bytes / 1024 / 1024).toFixed(2)} MB`} />
        <Tile title={t("admin.auditChain")} ok={h.audit_intact} value={h.audit_intact ? t("admin.intact") : t("admin.broken")}
          sub={t("admin.entries", { count: h.audit_entries })} />
        <Tile title={t("admin.validator")} ok value={h.validator_version} sub={`${t("chip.stt")} ${h.stt}`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* 2 · planning */}
        <Panel title={t("admin.planning")}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-muted"><th>{t("admin.method")}</th><th>n</th><th>p50</th><th>p95</th></tr></thead>
            <tbody>{m.planning.methods.map((x) => (
              <tr key={x.method} className="border-t border-line"><td>{t(`method.${x.method}`)}</td>
                <td className="num">{x.n}</td><td className="num">{x.p50 ?? "—"}</td><td className="num">{x.p95 ?? "—"}</td></tr>
            ))}</tbody>
          </table>
          <div className="mt-2 h-32">
            <ResponsiveContainer><BarChart data={status}><CartesianGrid stroke="#263038" vertical={false} />
              <XAxis dataKey="name" {...AXIS} /><YAxis allowDecimals={false} {...AXIS} width={28} /><Tooltip {...TIP} />
              <Bar dataKey="n" fill="#7C8B98" /></BarChart></ResponsiveContainer>
          </div>
          <p className="text-sm">{t("admin.fallbacks")}: <span className="num">{m.planning.greedy_fallbacks}</span> · {t("admin.feasibleShare")}:{" "}
            <span className="num">{Math.round(m.planning.feasible_share * 100)}%</span></p>
        </Panel>

        {/* 3 · validation */}
        <Panel title={t("admin.validation")}>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Stat label={t("admin.valid")} value={m.validation.valid} tone="text-valid" />
            <Stat label={t("admin.invalidFault")} value={m.validation.invalid_fault} tone="text-muted" />
            <Stat label={t("admin.invalidNoFault")} value={m.validation.invalid_without_fault}
              tone={m.validation.invalid_without_fault ? "text-conflict" : "text-valid"} />
          </div>
          <div className="mt-2 h-36">
            <ResponsiveContainer><BarChart data={rules}><CartesianGrid stroke="#263038" vertical={false} />
              <XAxis dataKey="name" {...AXIS} interval={0} angle={-20} textAnchor="end" height={44} />
              <YAxis allowDecimals={false} {...AXIS} width={28} /><Tooltip {...TIP} />
              <Bar dataKey="n" fill="#E5484D" /></BarChart></ResponsiveContainer>
          </div>
        </Panel>

        {/* 4 · AI */}
        <Panel title={t("admin.ai")}>
          <div className="flex flex-wrap items-center gap-4">
            <div className="h-32 w-32">
              <ResponsiveContainer><PieChart><Pie data={share} dataKey="value" nameKey="name" innerRadius={30} outerRadius={55}>
                {share.map((s) => <Cell key={s.name} fill={s.name === "llm" ? "#0E9AA7" : "#7C8B98"} />)}
              </Pie><Tooltip {...TIP} /></PieChart></ResponsiveContainer>
            </div>
            <ul className="space-y-1 text-sm">
              {share.map((s) => <li key={s.name}><span className="num">{s.name}</span>: <span className="num">{s.value}</span></li>)}
              <li>{t("admin.grounding")}: <span className="num">{m.ai.grounding_failures}</span></li>
              {Object.entries(m.ai.explainer).map(([k, v]) => <li key={k}>{t("chip.explainer")} {k}: <span className="num">{v}</span></li>)}
            </ul>
          </div>
          <p className="mt-2 text-xs text-muted">{t("admin.rejections")}:{" "}
            {Object.entries(m.ai.rejections).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</p>
        </Panel>

        {/* 5 · operations */}
        <Panel title={t("admin.operations", { from: hhmm(m.operations.from) })}>
          <div className="h-36">
            <ResponsiveContainer><BarChart data={m.operations.platforms}><CartesianGrid stroke="#263038" vertical={false} />
              <XAxis dataKey="platform" {...AXIS} /><YAxis domain={[0, 100]} unit="%" {...AXIS} width={40} /><Tooltip {...TIP} />
              <Bar dataKey="pct" fill="#5AA9FF" /></BarChart></ResponsiveContainer>
          </div>
          <p className="text-sm">{t("compare.totalHold")}: <span className="num">{m.operations.total_hold_min}</span> · {t("compare.unassigned")}:{" "}
            <span className="num">{m.operations.unassigned}</span> · {t("admin.confirmed")}:{" "}
            <span className="num">{m.operations.disruptions_over_time.reduce((a, b) => a + b.n, 0)}</span></p>
        </Panel>
      </div>

      {/* 6 · security */}
      <Panel title={t("admin.security")}>
        <div className="flex flex-wrap gap-4 text-sm">
          {["ok", "fail", "locked"].map((k) => (
            <Stat key={k} label={t(`admin.login.${k}`)} value={m.security.logins[k] ?? 0}
              tone={k === "ok" ? "text-valid" : (m.security.logins[k] ?? 0) ? "text-held" : "text-muted"} />
          ))}
          <div>
            <div className="label">{t("admin.refused")}</div>
            <div className="num">{Object.entries(m.security.refused_by_role).map(([k, v]) => `${k} ${v}`).join(" · ") || "0"}</div>
          </div>
          <div>
            <div className="label">{t("admin.users")}</div>
            <div className="num">{m.security.users.map((u) => `${u.username} (${u.role}${u.disabled ? ", off" : ""})`).join(" · ")}</div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function Tile({ title, value, sub, ok }: { title: string; value: string; sub: string; ok: boolean }) {
  return (
    <div className={`panel p-3 ${ok ? "" : "border-conflict"}`}>
      <div className="label">{title}</div>
      <div className="mt-1 flex items-center gap-2 font-semibold">
        <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-valid" : "bg-conflict"}`} /><span className="num">{value}</span>
      </div>
      <div className="num text-xs text-muted">{sub}</div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel p-3"><h2 className="label mb-2">{title}</h2>{children}</section>;
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div><div className="label">{label}</div><div className={`num text-2xl font-semibold ${tone}`}>{value}</div></div>;
}
