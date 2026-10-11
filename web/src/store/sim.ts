// zustand store: session, scenario, revisions, which plan is viewed, the sim clock (SPEC §15).
// Every view derives what it draws from (plan, t), so the 3D view cannot disagree with the validated plan.
import { create } from "zustand";
import type {
  Assignment, ChangeItem, ExplainResponse, Health, PlanResponse, RevisionOut, ScenarioInfo, ScenarioState, SessionOut,
  ValidationReport,
} from "../api/client";
import { api } from "../api/client";
import { hhmm } from "../lib/time";

export type ViewKey = "applied" | string;      // "applied" or a revision id
export type Speed = 1 | 10 | 60;
export type StationView = "3d" | "2d";
export type MainView = "station" | "gantt";

interface SimState {
  session: SessionOut | null;
  sessionChecked: boolean;
  health: Health | null;
  scenarios: ScenarioInfo[];
  scenario: ScenarioState | null;
  plan: PlanResponse | null;
  appliedOut: RevisionOut | null;           // the revision currently applied, when planned in this session
  scheduledReport: ValidationReport | null; // "Check as scheduled" result
  explanation: ExplainResponse | null;
  parserPath: "llm" | "regex" | null;
  sttPath: string | null;
  view: ViewKey;
  showBefore: boolean;
  t: number;
  speed: Speed;
  playing: boolean;
  selected: string | null;
  stationView: StationView;
  mainView: MainView;
  planNow: string;
  draftText: string;
  injectFault: boolean;
  busy: string | null;
  error: string | null;
  notice: string | null;

  setSession(s: SessionOut | null): void;
  setHealth(h: Health | null): void;
  setScenarios(s: ScenarioInfo[]): void;
  setScenario(s: ScenarioState, keepPlan?: boolean): void;
  setPlan(p: PlanResponse | null): void;
  setApplied(rid: string, state: ScenarioState): void;
  set<K extends keyof SimState>(k: K, v: SimState[K]): void;
  select(id: string | null): void;
  tick(dtSeconds: number): void;
  setT(t: number): void;
  refresh(): Promise<void>;
  run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined>;
}

export const useSim = create<SimState>((set, get) => ({
  session: null,
  sessionChecked: false,
  health: null,
  scenarios: [],
  scenario: null,
  plan: null,
  appliedOut: null,
  scheduledReport: null,
  explanation: null,
  parserPath: null,
  sttPath: null,
  view: "applied",
  showBefore: false,
  t: 720,
  speed: 10,
  playing: false,
  selected: null,
  stationView: "3d",
  mainView: "station",
  planNow: "12:00",
  draftText: "",
  injectFault: false,
  busy: null,
  error: null,
  notice: null,

  setSession: (s) => set({ session: s, sessionChecked: true }),
  setHealth: (h) => set({ health: h }),
  setScenarios: (s) => set({ scenarios: s }),
  setScenario: (s, keepPlan = false) => {
    const changed = get().scenario?.scenario_id !== s.scenario_id;
    set({
      scenario: s,
      planNow: changed ? hhmm(s.now) : get().planNow,
      t: changed ? s.now : get().t,
      ...(changed && !keepPlan ? { plan: null, appliedOut: null, scheduledReport: null, explanation: null, view: "applied", selected: null } : {}),
    });
  },
  setPlan: (p) => set({ plan: p, explanation: null, view: p?.revisions[0]?.revision.id ?? "applied", showBefore: false }),
  setApplied: (rid, state) => {
    const ro = get().plan?.revisions.find((r) => r.revision.id === rid) ?? null;
    set({ scenario: state, appliedOut: ro, view: "applied" });
  },
  set: (k, v) => set({ [k]: v } as Partial<SimState>),
  select: (id) => set({ selected: id }),
  tick: (dt) => {
    const { playing, speed, t } = get();
    if (!playing) return;
    const next = t + (speed * dt) / 1;           // speed = sim-minutes per real second
    set({ t: next > 1439 ? 1439 : next, playing: next < 1439 });
  },
  setT: (t) => set({ t: Math.max(0, Math.min(1439, t)) }),
  refresh: async () => {
    const s = await api.scenario();
    get().setScenario(s, true);
  },
  run: async (label, fn) => {
    set({ busy: label, error: null });
    try {
      return await fn();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      return undefined;
    } finally {
      set({ busy: null });
    }
  },
}));

// ── selectors ──

export function viewedRevision(s: Pick<SimState, "view" | "plan">): RevisionOut | null {
  if (s.view === "applied" || !s.plan) return null;
  return s.plan.revisions.find((r) => r.revision.id === s.view) ?? null;
}

export function viewedAssignments(s: Pick<SimState, "view" | "plan" | "scenario">): Assignment[] {
  const ro = viewedRevision(s);
  return ro ? ro.revision.assignments : s.scenario?.applied ?? [];
}

export function viewedChanges(s: Pick<SimState, "view" | "plan" | "appliedOut">): Map<string, ChangeItem> {
  const ro = viewedRevision(s) ?? s.appliedOut;
  return new Map((ro?.changes ?? []).map((c) => [c.train_id, c]));
}

export function viewedConflictTrains(s: Pick<SimState, "view" | "plan" | "scenario">): Set<string> {
  const ro = viewedRevision(s);
  const rep = ro ? ro.validation : s.scenario?.applied_validation;
  return new Set((rep?.conflicts ?? []).flatMap((c) => c.trains));
}

/** Delay tags: reported minutes per train (arrival + departure). */
export function delayTags(s: Pick<SimState, "scenario">): Map<string, number> {
  const m = new Map<string, number>();
  for (const d of s.scenario?.disruptions.delays ?? []) m.set(d.train_id, (m.get(d.train_id) ?? 0) + d.minutes);
  return m;
}

export type TrainState = "frozen" | "ontime" | "delayed" | "held" | "moved" | "unassigned" | "conflict";

export function trainState(a: Assignment, change: ChangeItem | undefined, conflicts: Set<string>, delayed: boolean, t: number): TrainState {
  if (conflicts.has(a.train_id)) return "conflict";
  if (a.status !== "ASSIGNED") return "unassigned";
  if (a.dep !== null && a.dep !== undefined && a.dep <= t) return "frozen";
  const cls = change?.cls;
  if (cls === "MOVED" || cls === "MOVED_HELD") return "moved";
  if (cls === "HELD") return "held";
  if (cls === "DELAYED" || delayed) return "delayed";
  return "ontime";
}

export const STATE_VAR: Record<TrainState, string> = {
  frozen: "var(--st-frozen)", ontime: "var(--st-ontime)", delayed: "var(--st-delayed)", held: "var(--st-held)",
  moved: "var(--st-moved)", unassigned: "var(--st-unassigned)", conflict: "var(--st-conflict)",
};
export const STATE_HEX: Record<TrainState, string> = {
  frozen: "#3A4652", ontime: "#2BB673", delayed: "#F2A33A", held: "#F27C38", moved: "#5AA9FF",
  unassigned: "#9AA4AE", conflict: "#E5484D",
};
