import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AuditEntry } from "../api/client";
import { useSim } from "../store/sim";

/** Recent hash-chained audit entries (§12). Verification of the chain is an admin action (§30). */
export default function Audit({ limit = 8 }: { limit?: number }) {
  const { t } = useTranslation();
  const plan = useSim((s) => s.plan);
  const applied = useSim((s) => s.scenario?.applied_revision_id);
  const source = useSim((s) => s.scenario?.scenario_id);
  const [rows, setRows] = useState<AuditEntry[]>([]);
  useEffect(() => { api.audit(limit).then(setRows).catch(() => undefined); }, [limit, plan, applied, source]);
  return (
    <section className="panel p-3" aria-labelledby="aud-h">
      <h2 id="aud-h" className="label">{t("panel.audit")}</h2>
      <ul className="mt-2 space-y-1 text-xs">
        {rows.map((r) => (
          <li key={r.seq} className="flex gap-2">
            <span className="num text-muted">#{r.seq}</span>
            <span className="num text-muted">{new Date(r.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}</span>
            <span className="font-semibold">{r.action}</span>
            <span className="truncate text-muted" title={r.summary}>{r.actor} · {r.summary}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
