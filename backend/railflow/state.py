"""Shared state helpers for the planner layer (SPEC §6, §43, §44, §47.2).

- split_delays(): cumulative arrival and departure delays, accounted separately
- pending_delays(): delays confirmed but not yet reflected in the applied plan
- frozen_and_movable(): split trains at `now` into fixed slots and movable trains
- candidates(): platform candidates for a train (required ∩ allowed ∩ capacity)
- occupancy_after() / affected_set(): two-stage replanning over the affected set (§44)

INDEPENDENCE: used by the planners, metrics and reasons. The validator must NOT import it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from .models import Assignment, Disruptions, PlanInput, Station, Train


# ─────────────────────────── delay accounting ───────────────────────────

def split_delays(disruptions: Disruptions) -> tuple[dict[str, int], dict[str, int]]:
    """Cumulative (arrival, departure) delay per train, as defaultdict(int)."""
    arr_d: dict[str, int] = defaultdict(int)
    dep_d: dict[str, int] = defaultdict(int)
    for d in disruptions.delays:
        (dep_d if d.kind == "departure" else arr_d)[d.train_id] += d.minutes
    return arr_d, dep_d


def pending_delays(inp: PlanInput) -> tuple[dict[str, int], dict[str, int]]:
    """Delays not yet reflected in the applied plan (total minus already applied)."""
    arr_t, dep_t = split_delays(inp.disruptions)
    arr_a, dep_a = split_delays(inp.applied_disruptions)
    arr_p: dict[str, int] = defaultdict(int)
    dep_p: dict[str, int] = defaultdict(int)
    for k in set(arr_t) | set(arr_a):
        arr_p[k] = max(0, arr_t[k] - arr_a[k])
    for k in set(dep_t) | set(dep_a):
        dep_p[k] = max(0, dep_t[k] - dep_a[k])
    return arr_p, dep_p


# ─────────────────────────── frozen / movable ───────────────────────────

def frozen_and_movable(
    inp: PlanInput,
    movable_ids: Optional[set[str]] = None,
) -> tuple[list[Assignment], list[Train]]:
    """Split the timetable into fixed assignments and movable trains.

    Fixed when, in the applied plan:
    - arrived (arr ≤ now) — departed or at platform: platform and arrival kept,
      departure later only by a pending departure delay (§43);
    - outside `movable_ids` (affected-set stage 1, §44): applied slot shifted by its
      pending delays.
    Everything else is movable. A train with no applied slot is always movable.
    """
    applied = inp.applied_plan()
    arr_p, dep_p = pending_delays(inp)
    frozen: list[Assignment] = []
    movable: list[Train] = []
    for t in inp.timetable.trains:
        a = applied.get(t.id)
        placed = a is not None and a.status == "ASSIGNED" and a.platform and a.arr is not None
        if placed and a.arr <= inp.now:
            frozen.append(Assignment.assigned(t.id, a.platform, a.arr, a.dep + dep_p[t.id]))
        elif placed and movable_ids is not None and t.id not in movable_ids:
            s = a.arr + arr_p[t.id]
            frozen.append(Assignment.assigned(t.id, a.platform, s, a.dep + arr_p[t.id] + dep_p[t.id], a.hold))
        else:
            movable.append(t)
    return frozen, movable


def is_frozen_at(a: Optional[Assignment], now: int) -> bool:
    return a is not None and a.status == "ASSIGNED" and a.arr is not None and a.arr <= now


# ─────────────────────────── candidates ───────────────────────────

def fits(train: Train, station: Station, pid: str) -> bool:
    p = station.platform(pid)
    if p is None:
        return False
    if train.type == "GDS":
        return (train.wagons or 0) <= p.goods_loop_wagons
    return (train.coaches or 0) <= p.length_coaches


def candidates(train: Train, station: Station) -> list[str]:
    """Platforms a movable train may use: required → allowed → all; always filtered by capacity (§47.3)."""
    if train.required_platform:
        pool = [train.required_platform]
    elif train.allowed_platforms:
        pool = list(train.allowed_platforms)
    else:
        pool = station.platform_ids
    return [p for p in pool if fits(train, station, p)]


# ─────────────────────────── affected set ───────────────────────────

def occupancy_after(
    applied: Optional[Iterable[Assignment]],
    disruptions: Disruptions,
) -> dict[str, tuple[str, int, int]]:
    """{train_id: (platform, arr, dep)} of the applied plan with the given delays applied."""
    arr_d, dep_d = split_delays(disruptions)
    occ: dict[str, tuple[str, int, int]] = {}
    for a in applied or []:
        if a.status != "ASSIGNED" or a.platform is None or a.arr is None or a.dep is None:
            continue
        occ[a.train_id] = (a.platform, a.arr + arr_d[a.train_id],
                           a.dep + arr_d[a.train_id] + dep_d[a.train_id])
    return occ


def affected_set(
    applied: Optional[Iterable[Assignment]],
    disruptions: Disruptions,
    gap: int,
    now: int = 0,
) -> set[str]:
    """Disrupted trains plus their cascade, to a fixed point (SPEC §44).

    Seed: trains named in a delay, plus trains whose slot (delays applied) meets a closure.
    Cascade: add any train whose slot now conflicts with an affected train's slot.
    Uses the planner's own occupancy helper, never the validator.
    """
    occ = occupancy_after(applied, disruptions)
    A: set[str] = {d.train_id for d in disruptions.delays}
    for tid, (p, a, d) in occ.items():
        if any(c.platform_id == p and a < c.end and c.start < d + gap for c in disruptions.closures):
            A.add(tid)
    grew = True
    while grew:
        grew = False
        for tid, (p, a, d) in occ.items():
            if tid in A:
                continue
            if any(x in occ and occ[x][0] == p and a < occ[x][2] + gap and occ[x][1] < d + gap for x in A):
                A.add(tid)
                grew = True
    return A


def plan_affected(inp: PlanInput) -> Optional[set[str]]:
    """Movable set for stage 1, or None when every train may move.

    With no disruptions (first assignment, §17 /api/assign) every train is movable.
    Otherwise the affected set is computed on the applied plan with only the
    delays it does not already reflect.
    """
    pending = pending_disruptions(inp)
    if not pending.delays and not pending.closures:
        return None
    return affected_set(inp.applied_plan().values(), pending, inp.station.min_gap, inp.now)


def pending_disruptions(inp: PlanInput) -> Disruptions:
    """Disruptions not yet reflected in the applied plan."""
    arr_p, dep_p = pending_delays(inp)
    from .models import Delay
    delays = [Delay(train_id=t, minutes=m, kind="arrival") for t, m in sorted(arr_p.items()) if m > 0]
    delays += [Delay(train_id=t, minutes=m, kind="departure") for t, m in sorted(dep_p.items()) if m > 0]
    applied_cl = {(c.platform_id, c.start, c.end) for c in inp.applied_disruptions.closures}
    closures = [c for c in inp.disruptions.closures if (c.platform_id, c.start, c.end) not in applied_cl]
    return Disruptions(delays=delays, closures=closures)
