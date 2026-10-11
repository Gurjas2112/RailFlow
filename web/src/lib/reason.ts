// Render backend {code, params} parts in the active language (§11, §37). IDs, times and minutes pass through untranslated.
import type { TFunction } from "i18next";
import type { Conflict, ReasonPart } from "../api/client";
import { hhmm } from "./time";

export function renderPart(t: TFunction, p: ReasonPart): string {
  return t(`reason.${p.code}`, { ...(p.params as Record<string, unknown>) });
}

export function renderParts(t: TFunction, parts: ReasonPart[] | undefined, sep = "; "): string {
  return (parts ?? []).map((p) => renderPart(t, p)).filter(Boolean).join(sep);
}

export function renderExplain(t: TFunction, parts: ReasonPart[]): string {
  return parts.map((p) => t(`explain.${p.code}`, { ...(p.params as Record<string, unknown>) })).filter(Boolean).join(" ");
}

export function renderProposalReason(t: TFunction, p: ReasonPart | null | undefined, fallback?: string | null): string {
  if (!p) return fallback ?? "";
  return t(`proposal.${p.code}`, { ...(p.params as Record<string, unknown>) });
}

/** "OVERLAP · PF 4 · 51214 ↔ 51215 · trains overlap 5 min (10 min of reserved platform time)" (§47.1). */
export function renderConflict(t: TFunction, c: Conflict): string {
  const pf = c.platform ? t("conflict.onPlatform", { platform: c.platform.replace(/^P/, "") }) : "";
  const trains = c.trains.join(" ↔ ");
  let measure = "";
  if (c.code === "OVERLAP") measure = t("conflict.measureOverlap", { stay: c.stay_overlap_min, reserved: c.reserved_overlap_min });
  else if (c.code === "GAP_VIOLATION") measure = t("conflict.measureGap", { short: c.clearance_shortfall_min });
  else if (c.code === "CLOSURE_VIOLATION") measure = t("conflict.measureClosure", { reserved: c.reserved_overlap_min, start: hhmm(c.start), end: hhmm(c.end) });
  else if (c.minutes != null && c.minutes > 0) measure = t("conflict.measureMinutes", { minutes: c.minutes });
  return [c.code, pf, trains, measure].filter(Boolean).join(" · ");
}

export function conflictDescription(t: TFunction, code: string): string {
  return t(`conflictDesc.${code}`);
}
