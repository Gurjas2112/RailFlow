"""Demo-only fault injection (SPEC §9 — fault injection, §47.7 S5).

After planning, one movable train is moved onto the platform of its nearest neighbour
(by arrival) so that the two overlap. The revision is flagged `fault_injected` and the UI
shows a red banner. The validator must catch it; Apply is then disabled.

Deterministic: the victim is the movable train with the smallest planner hold (held
trains first), the neighbour is the assigned train on another platform whose arrival is
nearest the victim's earliest arrival. The victim arrives `gap` minutes after the
neighbour, never earlier than it could, and keeps its dwell.
"""
from __future__ import annotations

from .models import Assignment, Revision


def inject_fault(rev: Revision, now: int, gap: int) -> Revision:
    """Return `rev` with one planted overlap (mutated in place), or unchanged if impossible."""
    if rev.failed:
        return rev
    placed = [a for a in rev.assignments
              if a.status == "ASSIGNED" and a.platform and a.arr is not None and a.dep is not None]
    movable = [a for a in placed if a.arr > now]
    movable.sort(key=lambda a: (a.hold == 0, a.hold, a.arr, a.train_id))
    for y in movable:
        e = y.arr - y.hold                                   # earliest possible arrival
        stay = y.dep - y.arr
        others = sorted((x for x in placed if x.platform != y.platform and x.train_id != y.train_id),
                        key=lambda x: (abs(x.arr - e), x.train_id))
        for x in others:
            arr = max(e, x.arr + gap)
            dep = arr + stay
            if arr < x.dep + gap and x.arr < dep + gap:      # reserved intervals intersect
                i = next(i for i, a in enumerate(rev.assignments) if a.train_id == y.train_id)
                rev.assignments[i] = Assignment.assigned(y.train_id, x.platform, arr, dep, arr - e)
                rev.fault_injected = True
                return rev
    return rev
