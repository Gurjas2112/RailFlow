"""Revision metrics (SPEC §10.2, §21, §44, §47).

All figures are relative to the applied plan (the scheduled platforms before the first apply):
- total_hold_min: Σ planner hold
- weighted_delay: Σ π·hold with π = 5 − priority
- platform_changes: assigned trains on a different platform than the applied plan
- unassigned: UNASSIGNED trains
- changed: trains whose platform or times differ from the applied plan, plus unassigned
- moved_outside_affected: changed trains outside the affected set (0 in stage 1 by construction)
"""
from __future__ import annotations

from .models import Metrics, PlanInput, Revision


def compute_metrics(revision: Revision, inp: PlanInput) -> Metrics:
    applied = inp.applied_plan()
    orig = inp.timetable.by_id()
    affected = set(revision.affected)
    m = Metrics(trains_total=len(inp.timetable.trains), trains_affected=len(affected))
    for a in revision.assignments:
        t = orig.get(a.train_id)
        if t is None:
            continue
        before = applied.get(a.train_id)
        if a.status == "UNASSIGNED":
            m.unassigned += 1
            m.changed += 1
            if affected and a.train_id not in affected:
                m.moved_outside_affected += 1
            continue
        m.total_hold_min += a.hold
        m.weighted_delay += (5 - t.priority) * a.hold
        moved = before is not None and before.status == "ASSIGNED" and before.platform != a.platform
        if moved:
            m.platform_changes += 1
        slot_changed = (before is None or before.status != "ASSIGNED"
                        or (before.platform, before.arr, before.dep) != (a.platform, a.arr, a.dep))
        if slot_changed:
            m.changed += 1
            if affected and a.train_id not in affected and (moved or a.hold):
                m.moved_outside_affected += 1
    return m
