"""The active scenario: station, timetable, applied plan, confirmed disruptions, clock (SPEC §4, §6).

One process owns it. Every change is also written to SQLite (scenarios, disruptions, revisions,
applied) so history survives a restart and every revision traces back to its exact input.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Optional

from . import config, db
from .models import (Assignment, Disruptions, PlanInput, Revision, RevisionOut, ScenarioInfo, ScenarioState,
                     Station, Timetable, TimetableIn, ValidationReport)
from .validator import validate

LOCK = threading.RLock()


def builtin_scenarios() -> list[ScenarioInfo]:
    path = config.DATA / "scenarios.json"
    return [ScenarioInfo.model_validate(s) for s in json.loads(path.read_text(encoding="utf-8"))]


def load_station() -> Station:
    return Station.model_validate_json((config.DATA / "station_shivneri.json").read_text(encoding="utf-8"))


def load_timetable(name: str) -> Timetable:
    safe = config.DATA / pathlib_name(name)
    return TimetableIn.model_validate_json(safe.read_text(encoding="utf-8")).to_timetable()


def pathlib_name(name: str) -> str:
    if "/" in name or "\\" in name or not name.endswith(".json"):
        raise ValueError("timetable_file must be a bare .json file name")
    return name


class ScenarioStore:
    def __init__(self) -> None:
        self.station: Optional[Station] = None
        self.timetable: Optional[Timetable] = None
        self.scenario_id = ""
        self.source = ""
        self.disruptions = Disruptions()
        self.applied_disruptions = Disruptions()
        self.applied: Optional[list[Assignment]] = None
        self.applied_revision_id: Optional[str] = None
        self.applied_method: Optional[str] = None
        self.now = 0
        self.revisions: dict[str, RevisionOut] = {}

    # ── loading ──
    def set(self, station: Station, timetable: Timetable, source: str, now: int, loaded_by: str) -> None:
        with LOCK:
            self.station, self.timetable, self.source, self.now = station, timetable, source, now
            self.disruptions, self.applied_disruptions = Disruptions(), Disruptions()
            self.applied, self.applied_revision_id, self.applied_method = None, None, None
            self.revisions = {}
            self.scenario_id = db.insert_scenario(db.get_conn(), station.model_dump(mode="json"),
                                                  TimetableIn.from_timetable(timetable).model_dump(mode="json"),
                                                  loaded_by, source)

    def load_builtin(self, sid: str, loaded_by: str) -> ScenarioInfo:
        sc = next((s for s in builtin_scenarios() if s.id == sid), None)
        if sc is None:
            raise KeyError(sid)
        self.set(load_station(), load_timetable(sc.timetable_file), sc.id, sc.now, loaded_by)
        return sc

    # ── views ──
    def ready(self) -> bool:
        return self.station is not None and self.timetable is not None

    def plan_input(self, now: Optional[int] = None, disruptions: Optional[Disruptions] = None) -> PlanInput:
        assert self.station and self.timetable
        return PlanInput(station=self.station, timetable=self.timetable, applied=self.applied,
                         applied_disruptions=self.applied_disruptions,
                         disruptions=disruptions if disruptions is not None else self.disruptions,
                         now=self.now if now is None else now)

    def applied_revision(self) -> Revision:
        return self.plan_input().applied_revision()

    def applied_validation(self) -> ValidationReport:
        assert self.station and self.timetable
        inp = self.plan_input()
        rev = inp.applied_revision()
        if self.applied is None:                         # scheduled platforms, no disruptions yet applied
            return validate(self.station, self.timetable, Disruptions(), rev, None, 0)
        return validate(self.station, self.timetable, self.applied_disruptions, rev, None, 0)

    def state(self) -> ScenarioState:
        assert self.station and self.timetable
        return ScenarioState(
            scenario_id=self.scenario_id, source=self.source, station=self.station,
            trains=self.timetable.trains, applied=list(self.plan_input().applied_plan().values()),
            applied_revision_id=self.applied_revision_id, applied_method=self.applied_method,
            applied_validation=self.applied_validation(), disruptions=self.disruptions,
            applied_disruptions=self.applied_disruptions, now=self.now)

    def utilisation(self, window: int = 180) -> dict[str, Any]:
        """Occupied minutes (incl. gap) per platform in [now, now + window) of the applied plan (§34 panel 5)."""
        if not self.ready():
            return {"platforms": [], "total_hold_min": 0, "unassigned": 0}
        assert self.station
        gap, lo, hi = self.station.min_gap, self.now, self.now + window
        busy = {p.id: 0 for p in self.station.platforms}
        hold = unassigned = 0
        for a in self.plan_input().applied_plan().values():
            if a.status != "ASSIGNED" or a.platform is None or a.arr is None or a.dep is None:
                unassigned += 1
                continue
            hold += a.hold
            busy[a.platform] = busy.get(a.platform, 0) + max(0, min(hi, a.dep + gap) - max(lo, a.arr))
        for c in self.disruptions.closures:
            busy[c.platform_id] = busy.get(c.platform_id, 0) + max(0, min(hi, c.end) - max(lo, c.start))
        return {"window_min": window, "from": lo,
                "platforms": [{"platform": p, "pct": round(min(100.0, 100 * m / window), 1)} for p, m in busy.items()],
                "total_hold_min": hold, "unassigned": unassigned}


store = ScenarioStore()
