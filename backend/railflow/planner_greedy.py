"""Greedy planner — baseline and CP-SAT fallback (SPEC §8).

Uses the same two-stage affected-set replanning as CP-SAT (§44).

Sorts movable trains by (has required platform first, earliest arrival, priority).
For each train, tries every candidate platform and picks the one needing the
smallest hold. Ties broken by keeping the base platform, then by platform ID.

This is the benchmark baseline and the fallback if CP-SAT returns no solution.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Assignment, PlanInput, Revision
from .state import candidates, frozen_and_movable, plan_affected, split_delays


def earliest_hold(
    busy: list[tuple[int, int]],
    s0: int,
    size: int,
    max_hold: int,
) -> int | None:
    """Find the smallest hold that fits a block of `size` starting at `s0 + hold`.

    `busy` is a sorted list of (start, end) occupied intervals on one platform.
    Returns the hold in minutes, or None if no placement fits within max_hold.
    """
    s = s0
    for a, b in sorted(busy):
        if s + size <= a:
            break
        s = max(s, b)
    hold = s - s0
    return hold if hold <= max_hold else None


def plan_greedy(inp: PlanInput, movable_ids: set[str] | None = None) -> Revision:
    """Run the greedy planner on the plan input."""
    st = inp.station
    gap = st.min_gap
    arr_d, dep_d = split_delays(inp.disruptions)
    frozen, movable = frozen_and_movable(inp, movable_ids)
    base = inp.base_platforms()

    # Build busy intervals from frozen trains and closures
    busy: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for a in frozen:
        if a.platform is not None and a.arr is not None and a.dep is not None:
            busy[a.platform].append((a.arr, a.dep + gap))
    for c in inp.disruptions.closures:
        busy[c.platform_id].append((c.start, c.end))

    # Sort: required platform first, then earliest arrival, then priority
    order = sorted(
        movable,
        key=lambda t: (
            t.required_platform is None,
            t.arr + arr_d[t.id],
            t.priority,
        ),
    )

    out = list(frozen)

    for t in order:
        e = t.arr + arr_d[t.id]                          # earliest arrival
        dwell = (t.dep - t.arr) + dep_d[t.id]            # dwell + departure delay
        best: tuple | None = None

        for p in candidates(t, st):
            h = earliest_hold(busy[p], e, dwell + gap, st.max_hold)
            if h is not None:
                # Tie-break: smallest hold, prefer base platform, then alphabetic
                key = (h, p != base.get(t.id), p)
                if best is None or key < best[0]:
                    best = (key, p, h)

        if best is None:
            out.append(Assignment.unassigned(t.id, reason_code="NO_SLOT_WITHIN_MAX_HOLD"))
            continue

        _, p, h = best
        busy[p].append((e + h, e + h + dwell + gap))
        out.append(Assignment.assigned(t.id, p, e + h, e + h + dwell, h))

    return Revision(
        method="greedy",
        assignments=out,
        solver_status="HEURISTIC",
        solve_ms=0,
    )


def plan(inp: PlanInput) -> Revision:
    """Two-stage affected-set greedy (SPEC §44); widens if stage 1 leaves anyone unassigned."""
    A = plan_affected(inp)
    rev = plan_greedy(inp, movable_ids=A)
    if A is not None and rev.unassigned_count():
        rev = plan_greedy(inp, movable_ids=None)
        rev.widened = True
        rev.widened_reason = "No placement using affected trains only; widened to all movable trains"
    rev.affected = sorted(A or [])
    return rev
