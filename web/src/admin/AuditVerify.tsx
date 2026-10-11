import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AuditEntry, type AuditVerify as Verify } from "../api/client";

/** Walk the SHA-256 chain; show the first broken seq, if any (§12). */
export default function AuditVerify() {
  const { t } = useTranslation();
  const [v, setV] = useState<Verify | null>(null);
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const run = () => { api.auditVerify().then(setV).catch(() => undefined); api.audit(100).then(setRows).catch(() => undefined); };
  useEffect(run, []);
  return (
    <section className="panel space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="label">{t("admin.audit")}</h2>
        {v && (
          <span className={`font-semibold ${v.intact ? "text-valid" : "text-conflict"}`}>
            {v.intact ? t("admin.chainIntact", { count: v.entries }) : t("admin.chainBroken", { seq: v.first_broken_seq })}
          </span>
        )}
        <button type="button" className="btn btn-ghost btn-sm" onClick={run}>{t("admin.verify")}</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead><tr className="text-left text-muted"><th>seq</th><th>{t("admin.time")}</th><th>{t("admin.actor")}</th>
            <th>{t("admin.action")}</th><th>{t("admin.summary")}</th><th>hash</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.seq} className={`border-t border-line ${v?.first_broken_seq === r.seq ? "bg-conflict/20" : ""}`}>
              <td className="num">{r.seq}</td>
              <td className="num">{new Date(r.ts * 1000).toLocaleString([], { hour12: false })}</td>
              <td>{r.actor}</td><td className="font-semibold">{r.action}</td><td>{r.summary}</td>
              <td className="num text-muted">{r.hash.slice(0, 12)}…</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}
