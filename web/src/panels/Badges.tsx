import { useTranslation } from "react-i18next";
import type { RevisionOut, ValidationReport } from "../api/client";

/** Verdict from validator.py only (§14, §47.6). */
export function ValidatorBadge({ report, compact = false }: { report: ValidationReport | null | undefined; compact?: boolean }) {
  const { t } = useTranslation();
  if (!report) return null;
  const n = report.conflicts.length;
  return (
    <span role="status" className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-sm font-semibold ${
      report.valid ? "bg-valid/15 text-valid" : "bg-invalid/15 text-invalid"}`}>
      <span aria-hidden className={`h-2 w-2 rounded-full ${report.valid ? "bg-valid" : "bg-invalid"}`} />
      {report.valid ? (compact ? t("verdict.valid") : t("verdict.validated", { count: n })) : t("verdict.invalid", { count: n })}
    </span>
  );
}

/** Recovery badge — content and solver status, never the validator (§47.6). */
export function RecoveryBadge({ ro }: { ro: RevisionOut }) {
  const { t } = useTranslation();
  const r = ro.recovery;
  const cls = r === "FULLY_ASSIGNED" ? "border-ontime/50 text-ontime" : r === "PARTIAL" ? "border-unassigned text-unassigned" : "border-held text-held";
  return (
    <span className={`chip ${cls}`}>
      {r === "PARTIAL" ? t("recovery.PARTIAL", { count: ro.metrics.unassigned }) : t(`recovery.${r}`)}
    </span>
  );
}

export function PathChip({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <span className={`chip ${warn ? "border-held/60 text-held" : ""}`}>
      <span>{label}</span>
      <span className="num text-ink">{value}</span>
    </span>
  );
}
