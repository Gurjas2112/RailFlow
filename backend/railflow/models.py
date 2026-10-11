"""RailFlow data models — the ONLY module shared by the planner and the validator (SPEC §6, §32).

Times are integer minutes since 00:00 inside the system; HH:MM strings at input edges
(timetable files, disruption confirmations). Plan outputs carry integer minutes.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .timeutil import to_hhmm, to_min

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
TRAIN_ID = r"^(\d{5}|GDS-\d{4})$"
PLATFORM_ID = r"^P\d{1,2}$"
TrainType = Literal["SF", "MEX", "PAS", "MEMU", "GDS"]
Lang = Literal["en", "hi", "mr"]

VALIDATOR_RULES = ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10"]
RULE_OF = {
    "MISSING_TRAIN": "V1", "DUPLICATE_TRAIN": "V1", "UNKNOWN_TRAIN": "V1",
    "UNKNOWN_PLATFORM": "V2",
    "REQUIRED_PLATFORM": "V3", "NOT_ALLOWED_PLATFORM": "V3",
    "DWELL_CHANGED": "V4", "BAD_TIMES": "V4",
    "EARLIER_THAN_POSSIBLE": "V5",
    "HOLD_EXCEEDED": "V6",
    "FROZEN_CHANGED": "V7",
    "GAP_VIOLATION": "V8", "OVERLAP": "V8",
    "CLOSURE_VIOLATION": "V9",
    "CAPACITY_EXCEEDED": "V10",
    "UNASSIGNED_WITHOUT_REASON": "—",
}


# ───────────────────────────── station ─────────────────────────────

class Platform(BaseModel):
    id: str = Field(pattern=PLATFORM_ID)
    name: str = Field(max_length=40)
    length_coaches: int = Field(ge=0, le=60)
    use: str = Field(default="", max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=40)
    goods_loop_wagons: int = Field(default=0, ge=0, le=200)


class Station(BaseModel):
    id: str = Field(min_length=2, max_length=8)
    code: str = Field(default="", max_length=8)
    name: str = Field(max_length=80)
    min_gap: int = Field(ge=0, le=30)
    max_hold: int = Field(default=45, ge=0, le=180)
    platforms: list[Platform] = Field(min_length=1, max_length=20)
    capacity_rule: Optional[str] = None
    model_routes: bool = False                       # Tier 3 (SPEC §48) — off by default

    @model_validator(mode="after")
    def _unique(self):
        ids = [p.id for p in self.platforms]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate platform IDs")
        seen: dict[str, str] = {}
        for p in self.platforms:
            for a in p.aliases:
                k = " ".join(a.lower().split())
                if k in seen and seen[k] != p.id:
                    raise ValueError(f"alias {a!r} used by {seen[k]} and {p.id}")
                seen[k] = p.id
        return self

    def platform(self, pid: str | None) -> Optional[Platform]:
        return next((p for p in self.platforms if p.id == pid), None)

    @property
    def platform_ids(self) -> list[str]:
        return [p.id for p in self.platforms]


# ───────────────────────────── timetable ─────────────────────────────

class Train(BaseModel):
    """Internal train: times in minutes."""
    id: str = Field(pattern=TRAIN_ID)
    name: str = ""
    type: TrainType
    origin: str = ""
    destination: str = ""
    direction: Literal["UP", "DN"] = "DN"
    arr: int = Field(ge=0, le=1439)
    dep: int = Field(ge=1, le=1439)
    platform: Optional[str] = None
    required_platform: Optional[str] = None
    allowed_platforms: list[str] = Field(default_factory=list)
    coaches: Optional[int] = None
    wagons: Optional[int] = None
    days: str = "Daily"
    priority: int = Field(ge=1, le=4)

    @property
    def dwell(self) -> int:
        return self.dep - self.arr


class Timetable(BaseModel):
    station: str = "SVNJ"
    day: str = "Sun"
    trains: list[Train]

    def by_id(self) -> dict[str, Train]:
        return {t.id: t for t in self.trains}


class TrainIn(BaseModel):
    """Edge model (SPEC §32 layer 2): HH:MM strings, IR working-timetable fields."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(pattern=TRAIN_ID)
    name: str = Field(max_length=60)
    type: TrainType
    origin: str = Field(pattern=r"^[A-Z]{2,5}$")
    destination: str = Field(pattern=r"^[A-Z]{2,5}$")
    direction: Literal["UP", "DN"]
    coaches: Optional[int] = Field(default=None, ge=1, le=60)
    wagons: Optional[int] = Field(default=None, ge=1, le=200)
    days: str = Field(default="Daily", max_length=40)
    arr: str = Field(pattern=HHMM)
    dep: str = Field(pattern=HHMM)
    platform: Optional[str] = Field(default=None, pattern=PLATFORM_ID)
    required_platform: Optional[str] = Field(default=None, pattern=PLATFORM_ID)
    allowed_platforms: list[str] = Field(default_factory=list, max_length=20)
    priority: int = Field(ge=1, le=4)

    @field_validator("allowed_platforms")
    @classmethod
    def _pf_ids(cls, v: list[str]):
        import re
        for p in v:
            if not re.match(PLATFORM_ID, p):
                raise ValueError(f"allowed platform {p!r} is not like P3")
        return v

    @model_validator(mode="after")
    def times_and_platforms(self):
        if to_min(self.dep) <= to_min(self.arr):
            raise ValueError(f"{self.id}: departure must be after arrival")
        if to_min(self.dep) - to_min(self.arr) > 180:
            raise ValueError(f"{self.id}: dwell over 180 min")
        if self.required_platform and self.allowed_platforms and \
                self.required_platform not in self.allowed_platforms:
            raise ValueError(f"{self.id}: required platform not in allowed platforms")
        if self.type == "GDS":
            if self.wagons is None or self.coaches is not None:
                raise ValueError(f"{self.id}: goods trains carry wagons, never coaches")
        elif self.coaches is None or self.wagons is not None:
            raise ValueError(f"{self.id}: passenger trains carry coaches, never wagons")
        return self

    def to_train(self) -> Train:
        d = self.model_dump()
        d["arr"], d["dep"] = to_min(self.arr), to_min(self.dep)
        return Train(**d)


class TimetableIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    station: str = "SVNJ"
    day: str = "Sun"
    trains: list[TrainIn] = Field(min_length=1, max_length=200)

    @field_validator("trains")
    @classmethod
    def unique_ids(cls, v):
        ids = [t.id for t in v]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"duplicate train IDs: {dup}")
        return v

    def to_timetable(self) -> Timetable:
        return Timetable(station=self.station, day=self.day, trains=[t.to_train() for t in self.trains])

    @classmethod
    def from_timetable(cls, tt: Timetable) -> "TimetableIn":
        rows = []
        for t in tt.trains:
            d = t.model_dump()
            d["arr"], d["dep"] = to_hhmm(t.arr), to_hhmm(t.dep)
            rows.append(d)
        return cls(station=tt.station, day=tt.day, trains=rows)


def referential_errors(station: Station, tt: Timetable | TimetableIn) -> list[str]:
    """SPEC §32 layer 3: references resolve and stock fits every allowed PF."""
    errs: list[str] = []
    for t in tt.trains:
        for field in ("platform", "required_platform"):
            pid = getattr(t, field)
            if pid and station.platform(pid) is None:
                errs.append(f"{t.id}: {field.replace('_', ' ')} {pid} does not exist")
        for pid in t.allowed_platforms:
            p = station.platform(pid)
            if p is None:
                errs.append(f"{t.id}: allowed platform {pid} does not exist")
            elif t.type == "GDS" and (t.wagons or 0) > p.goods_loop_wagons:
                errs.append(f"{t.id}: {t.wagons} wagons do not fit {pid} (goods loop {p.goods_loop_wagons})")
            elif t.type != "GDS" and (t.coaches or 0) > p.length_coaches:
                errs.append(f"{t.id}: {t.coaches} coaches do not fit {pid} ({p.length_coaches})")
    return errs


# ───────────────────────────── disruptions ─────────────────────────────

class Delay(BaseModel):
    train_id: str = Field(pattern=TRAIN_ID)
    minutes: int = Field(ge=1, le=600)
    kind: Literal["arrival", "departure"] = "arrival"
    source_span: Optional[str] = Field(default=None, max_length=1000)


class Closure(BaseModel):
    platform_id: str = Field(pattern=PLATFORM_ID)
    start: int = Field(ge=0, le=1439)
    end: int = Field(ge=1, le=1440)
    source_span: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _order(self):
        if self.start >= self.end:
            raise ValueError("closure start must be before end")
        return self


class Disruptions(BaseModel):
    delays: list[Delay] = Field(default_factory=list)
    closures: list[Closure] = Field(default_factory=list)

    def merged(self, other: "Disruptions") -> "Disruptions":
        return Disruptions(delays=self.delays + other.delays, closures=self.closures + other.closures)

    def summary(self) -> list[str]:
        out = [f"{d.train_id} {'departure' if d.kind == 'departure' else 'arrival'} +{d.minutes} min" for d in self.delays]
        out += [f"{c.platform_id} closed {to_hhmm(c.start)}–{to_hhmm(c.end)}" for c in self.closures]
        return out


class DelayIn(BaseModel):
    """Confirmed delay as sent by the browser after the human gate."""
    type: Literal["delay"] = "delay"
    train_id: str = Field(pattern=TRAIN_ID)
    minutes: int = Field(ge=1, le=600)
    kind: Literal["arrival", "departure"] = "arrival"
    source: Optional[str] = Field(default=None, max_length=1000)


class ClosureIn(BaseModel):
    type: Literal["closure"] = "closure"
    platform_id: str = Field(pattern=PLATFORM_ID)
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    source: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _order(self):
        if to_min(self.start) >= to_min(self.end):
            raise ValueError("closure start must be before end")
        return self


Disruption = Annotated[Union[DelayIn, ClosureIn], Field(discriminator="type")]


def disruptions_from_in(items: list[DelayIn | ClosureIn]) -> Disruptions:
    d = Disruptions()
    for it in items:
        if isinstance(it, DelayIn):
            d.delays.append(Delay(train_id=it.train_id, minutes=it.minutes, kind=it.kind, source_span=it.source))
        else:
            d.closures.append(Closure(platform_id=it.platform_id, start=to_min(it.start), end=to_min(it.end),
                                      source_span=it.source))
    return d


# ───────────────────────────── plans and verdicts ─────────────────────────────

class Assignment(BaseModel):
    train_id: str
    status: Literal["ASSIGNED", "UNASSIGNED"]
    platform: Optional[str] = None
    arr: Optional[int] = None
    dep: Optional[int] = None
    hold: int = 0                                     # minutes added by the planner beyond reported delay
    reason_code: Optional[str] = None

    @classmethod
    def assigned(cls, tid: str, platform: str, arr: int, dep: int, hold: int = 0) -> "Assignment":
        return cls(train_id=tid, status="ASSIGNED", platform=platform, arr=arr, dep=dep, hold=hold)

    @classmethod
    def unassigned(cls, tid: str, reason_code: Optional[str]) -> "Assignment":
        return cls(train_id=tid, status="UNASSIGNED", reason_code=reason_code)


class Conflict(BaseModel):
    code: str
    trains: list[str]
    platform: Optional[str] = None
    minutes: Optional[int] = None                     # V5, V6, V10 only (SPEC §47.1)
    stay_overlap_min: Optional[int] = None
    clearance_shortfall_min: Optional[int] = None
    reserved_overlap_min: Optional[int] = None
    start: Optional[int] = None                       # closure window for V9
    end: Optional[int] = None
    rule: str = ""

    @model_validator(mode="after")
    def _rule(self):
        if not self.rule:
            self.rule = RULE_OF.get(self.code, "—")
        return self


class ValidationReport(BaseModel):
    valid: bool
    conflicts: list[Conflict] = Field(default_factory=list)
    checked_rules: list[str] = Field(default_factory=lambda: list(VALIDATOR_RULES))
    validator_version: str = ""


class Revision(BaseModel):
    """A planner output. Never trusted until validated."""
    id: str = ""
    method: str
    assignments: list[Assignment] = Field(default_factory=list)
    solver_status: str = "UNKNOWN"
    solve_ms: int = 0
    stages: list[dict[str, Any]] = Field(default_factory=list)
    failed: bool = False
    affected: list[str] = Field(default_factory=list)
    widened: bool = False
    widened_reason: Optional[str] = None
    fault_injected: bool = False

    @classmethod
    def solver_failed(cls, method: str, status: str, stages: list[dict[str, Any]] | None = None) -> "Revision":
        return cls(method=method, solver_status=status, stages=stages or [], failed=True)

    def unassigned_count(self) -> int:
        return sum(1 for a in self.assignments if a.status == "UNASSIGNED")

    def by_train(self) -> dict[str, Assignment]:
        return {a.train_id: a for a in self.assignments}


def recovery_status(rev: Revision) -> str:
    """Recovery badge (SPEC §47.6) — content and solver status, never the validator."""
    if rev.failed:
        return "SOLVER_FAILED"
    return "PARTIAL" if rev.unassigned_count() else "FULLY_ASSIGNED"


class PlanInput(BaseModel):
    station: Station
    timetable: Timetable
    applied: Optional[list[Assignment]] = None        # None → the scheduled platforms are the applied plan
    applied_disruptions: Disruptions = Field(default_factory=Disruptions)   # already reflected in `applied`
    disruptions: Disruptions = Field(default_factory=Disruptions)           # cumulative, incl. new ones
    now: int = 0

    def applied_plan(self) -> dict[str, Assignment]:
        if self.applied is not None:
            return {a.train_id: a for a in self.applied}
        return {t.id: (Assignment.assigned(t.id, t.platform, t.arr, t.dep) if t.platform
                       else Assignment.unassigned(t.id, None)) for t in self.timetable.trains}

    def base_platforms(self) -> dict[str, str]:
        out: dict[str, str] = {}
        ap = self.applied_plan()
        for t in self.timetable.trains:
            a = ap.get(t.id)
            if a and a.status == "ASSIGNED" and a.platform:
                out[t.id] = a.platform
            elif t.platform:
                out[t.id] = t.platform
        return out

    def applied_revision(self) -> Revision:
        return Revision(method="applied", assignments=list(self.applied_plan().values()))


# ───────────────────────────── API shapes ─────────────────────────────

class ReasonPart(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class Slot(BaseModel):
    platform: Optional[str] = None
    arr: Optional[int] = None
    dep: Optional[int] = None


class ChangeItem(BaseModel):
    train_id: str
    cls: str                                          # FROZEN · UNCHANGED · DELAYED · HELD · MOVED · MOVED_HELD · UNASSIGNED
    before: Optional[Slot] = None
    after: Slot
    hold: int = 0
    parts: list[ReasonPart] = Field(default_factory=list)
    text: str = ""
    caused_by: list[str] = Field(default_factory=list)
    affected: bool = False


class Metrics(BaseModel):
    total_hold_min: int = 0
    weighted_delay: int = 0
    platform_changes: int = 0
    unassigned: int = 0
    trains_affected: int = 0
    trains_total: int = 0
    changed: int = 0
    moved_outside_affected: int = 0


class RevisionOut(BaseModel):
    revision: Revision
    validation: ValidationReport
    recovery: str
    metrics: Metrics
    changes: list[ChangeItem]
    label: str = ""
    sha256: str = ""


class PlanResponse(BaseModel):
    revisions: list[RevisionOut]
    affected: list[str] = Field(default_factory=list)
    now: int = 0
    disruptions: list[str] = Field(default_factory=list)
    agree: bool = False                               # every revision has the same assignments
    fault_injected: bool = False
    widened: bool = False


class Proposal(BaseModel):
    id: str
    type: Literal["delay", "closure"]
    status: Literal["ok", "needs_clarification", "rejected"] = "ok"
    train_id: Optional[str] = None
    train_ref: Optional[str] = None
    minutes: Optional[int] = None
    kind: Optional[Literal["arrival", "departure"]] = None
    platform_id: Optional[str] = None
    platform_ref: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    source: str = ""
    span: Optional[list[int]] = None
    ambiguous: bool = False
    reason: Optional[ReasonPart] = None
    message: Optional[str] = None


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    now: Optional[str] = Field(default=None, pattern=HHMM)


class ParseResponse(BaseModel):
    proposals: list[Proposal]
    rejected: list[Proposal]
    unparsed: list[str]
    parser_path: Literal["llm", "regex"]
    ms: int = 0


class PlanRequest(BaseModel):
    confirmed: list[Disruption] = Field(default_factory=list, max_length=20)
    now: str = Field(pattern=HHMM)
    inject_fault: bool = False
    source_text: Optional[str] = Field(default=None, max_length=1000)
    parser_path: Literal["llm", "regex", "manual"] = "manual"


class AssignRequest(BaseModel):
    now: Optional[str] = Field(default=None, pattern=HHMM)


class ExplainRequest(BaseModel):
    revision_ids: list[str] = Field(min_length=1, max_length=3)
    lang: Lang = "en"


class ExplainResponse(BaseModel):
    text: str
    explainer_path: Literal["llm", "template"]
    grounding: str
    parts: list[ReasonPart] = Field(default_factory=list)


class ScenarioLoadRequest(BaseModel):
    scenario_id: Optional[str] = Field(default=None, max_length=40)
    station: Optional[dict[str, Any]] = None
    timetable: Optional[dict[str, Any]] = None
    source: Optional[str] = Field(default=None, max_length=200)


class ScenarioInfo(BaseModel):
    id: str
    name: str
    timetable_file: str
    now: int
    text: Optional[str] = None
    inject_fault: bool = False
    expect: Optional[str] = None
    proves: str = ""


class ScenarioState(BaseModel):
    """Everything the browser renders: the station, the trains, the applied plan and its verdict."""
    scenario_id: str
    source: str
    station: Station
    trains: list[Train]
    applied: list[Assignment]
    applied_revision_id: Optional[str] = None
    applied_method: Optional[str] = None
    applied_validation: ValidationReport
    disruptions: Disruptions
    applied_disruptions: Disruptions
    now: int


class UploadResponse(BaseModel):
    timetable: Optional[dict[str, Any]] = None
    station: Optional[dict[str, Any]] = None
    needs_sheet: Optional[list[str]] = None
    errors: Optional[list[str]] = None
    excluded: list[str] = Field(default_factory=list)
    sha256: str = ""
    sheet: Optional[str] = None


class TranscribeResponse(BaseModel):
    transcript: str
    stt_path: Literal["whisper-small", "unavailable"]
    ms: int = 0
    error: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    user: str
    role: Literal["viewer", "controller", "admin"]
    lang: Lang = "en"


class LangRequest(BaseModel):
    lang: Lang


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class InviteRequest(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9_.-]{3,32}$")
    role: Literal["viewer", "controller", "admin"] = "viewer"


class InviteOut(BaseModel):
    username: str
    role: str
    token: str
    link: str
    expires_in_s: int = 86400


class UserPatch(BaseModel):
    role: Optional[Literal["viewer", "controller", "admin"]] = None
    disabled: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    disabled: bool
    lang: str = "en"


class AuditVerify(BaseModel):
    intact: bool
    entries: int
    first_broken_seq: Optional[int] = None


class Health(BaseModel):
    ok: bool
    ollama: Literal["up", "down"]
    model: str
    validator_version: str
    db: str = "ok"
    stt: str = "unavailable"
    audit: str = "intact"
