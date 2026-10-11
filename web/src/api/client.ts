// Typed API client. Types come from the generated OpenAPI schema (src/api/schema.d.ts, `npm run gen:api`).
import type { components } from "./schema";

type S = components["schemas"];
export type Station = S["Station"];
export type Train = S["Train"];
export type Assignment = S["Assignment"];
export type Conflict = S["Conflict"];
export type ValidationReport = S["ValidationReport"];
export type Disruptions = S["Disruptions"];
export type ScenarioState = S["ScenarioState"];
export type ScenarioInfo = S["ScenarioInfo"];
export type PlanResponse = S["PlanResponse"];
export type RevisionOut = S["RevisionOut"];
export type ChangeItem = S["ChangeItem"];
export type ReasonPart = S["ReasonPart"];
export type Proposal = S["Proposal"];
export type ParseResponse = S["ParseResponse"];
export type ExplainResponse = S["ExplainResponse"];
export type Health = S["Health"];
export type SessionOut = S["SessionOut"];
export type Role = SessionOut["role"];
export type Lang = "en" | "hi" | "mr";
export type UploadResponse = S["UploadResponse"];
export type TranscribeResponse = S["TranscribeResponse"];
export type UserOut = S["UserOut"];
export type InviteOut = S["InviteOut"];
export type AuditVerify = S["AuditVerify"];
export type ConfirmedDelay = S["DelayIn"];
export type ConfirmedClosure = S["ClosureIn"];
export type Confirmed = ConfirmedDelay | ConfirmedClosure;

export interface AuditEntry {
  seq: number; ts: number; actor: string; action: string; payload_hash: string | null; summary: string; hash: string;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ")
      : `HTTP ${status}`);
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const r = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "content-type": "application/json" } : undefined,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    if (r.status === 401 && onUnauthorized && !path.startsWith("/api/auth/login")) onUnauthorized();
    // upload errors come back as an UploadResponse body with status 422
    if (r.status === 422 && data && typeof data === "object" && "errors" in data) return data as T;
    throw new ApiError(r.status, data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data);
  }
  return data as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  me: () => request<SessionOut>("GET", "/api/auth/me"),
  login: (username: string, password: string) => request<SessionOut>("POST", "/api/auth/login", { username, password }),
  logout: () => request<void>("POST", "/api/auth/logout"),
  setLang: (lang: Lang) => request<SessionOut>("PATCH", "/api/auth/me", { lang }),
  acceptInvite: (token: string, password: string) => request<SessionOut>("POST", "/api/auth/accept-invite", { token, password }),

  scenarios: () => request<ScenarioInfo[]>("GET", "/api/scenarios"),
  scenario: () => request<ScenarioState>("GET", "/api/scenario"),
  load: (scenario_id: string) => request<ScenarioState>("POST", "/api/scenario/load", { scenario_id }),
  loadCustom: (station: unknown, timetable: unknown, source: string) =>
    request<ScenarioState>("POST", "/api/scenario/load", { station, timetable, source }),
  reset: () => request<ScenarioState>("POST", "/api/scenario/reset"),
  validateScheduled: () => request<ValidationReport>("POST", "/api/validate/scheduled"),
  assign: (now: string) => request<PlanResponse>("POST", "/api/assign", { now }),
  parse: (text: string, now: string) => request<ParseResponse>("POST", "/api/disruptions/parse", { text, now }),
  plan: (confirmed: Confirmed[], now: string, inject_fault: boolean, source_text: string, parser_path: "llm" | "regex" | "manual") =>
    request<PlanResponse>("POST", "/api/plan", { confirmed, now, inject_fault, source_text, parser_path }),
  explain: (revision_ids: string[], lang: Lang) => request<ExplainResponse>("POST", "/api/explain", { revision_ids, lang }),
  apply: (rid: string) => request<ScenarioState>("POST", `/api/revisions/${encodeURIComponent(rid)}/apply`),
  upload: (file: File, sheet?: string) => {
    const f = new FormData();
    f.append("file", file);
    if (sheet) f.append("sheet", sheet);
    return request<UploadResponse>("POST", "/api/timetable/upload", undefined, f);
  },
  transcribe: (file: Blob, name: string, lang: Lang) => {
    const f = new FormData();
    f.append("file", file, name);
    f.append("lang", lang);
    return request<TranscribeResponse>("POST", "/api/disruptions/transcribe", undefined, f);
  },
  audit: (limit = 200) => request<AuditEntry[]>("GET", `/api/audit?limit=${limit}`),
  auditVerify: () => request<AuditVerify>("GET", "/api/audit/verify"),

  users: () => request<UserOut[]>("GET", "/api/admin/users"),
  invite: (username: string, role: Role) => request<InviteOut>("POST", "/api/admin/users/invite", { username, role }),
  patchUser: (ref: string, patch: { role?: Role; disabled?: boolean }) =>
    request<UserOut>("PATCH", `/api/admin/users/${encodeURIComponent(ref)}`, patch),
  metrics: (window: number) => request<AdminMetrics>("GET", `/api/admin/metrics?window=${window}`),
};

export interface Pctl { method: string; n: number; p50: number | null; p95: number | null }
export interface AdminMetrics {
  window_min: number;
  health: { api: string; ollama: string; model: string; db: string; db_bytes: number; audit_intact: boolean;
    audit_entries: number; first_broken_seq: number | null; validator_version: string; stt: string;
    ollama_down_s: number; api_p95_ms: number | null; requests: number };
  planning: { methods: Pctl[]; status: Record<string, number>; greedy_fallbacks: number; feasible_share: number };
  validation: { valid: number; invalid_fault: number; invalid_without_fault: number; by_rule: Record<string, number> };
  ai: { parser_share: Record<string, number>; parse_p50_ms: number | null; rejections: Record<string, number>;
    explainer: Record<string, number>; grounding_failures: number };
  operations: { window_min: number; from: number; platforms: { platform: string; pct: number }[]; total_hold_min: number;
    unassigned: number; disruptions_over_time: { ts: number; n: number }[] };
  security: { logins: Record<string, number>; refused_by_role: Record<string, number>; users: UserOut[] };
  alerts: string[];
}
