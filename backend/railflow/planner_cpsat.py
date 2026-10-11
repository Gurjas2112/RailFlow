"""CP-SAT planner — primary solver (SPEC §7).

Sequential lexicographic objective (v1.6):
- Level 1: minimise priority-weighted unassigned
- Level 2/3: min-delay → (delay, changes) or min-changes → (changes, delay)

Uses affected-set replanning (§44): only affected trains may move in stage 1;
widens to all movable trains if stage 1 leaves any UNASSIGNED.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from ortools.sat.python import cp_model

from .models import Assignment, PlanInput, Revision
from .state import candidates, frozen_and_movable, plan_affected, split_delays

ORDER = {
    "cpsat_min_delay":   ("unassigned", "delay", "changes"),
    "cpsat_min_changes": ("unassigned", "changes", "delay"),
}
STAGE_SECONDS = 2.0  # per level; 3 levels ≈ 6 s worst case


def plan_cpsat(
    inp: PlanInput,
    method: str,
    movable_ids: Optional[set[str]] = None,
) -> Revision:
    """Run CP-SAT on the plan input with the given method and movable set."""
    st = inp.station
    gap = st.min_gap
    max_hold = st.max_hold
    arr_d, dep_d = split_delays(inp.disruptions)
    frozen, movable = frozen_and_movable(inp, movable_ids)
    base = inp.base_platforms()

    m = cp_model.CpModel()
    on_p: dict[str, list] = defaultdict(list)
    dec: dict[str, tuple] = {}

    # Fixed intervals for frozen trains
    for a in frozen:
        if a.platform is not None and a.arr is not None and a.dep is not None:
            size = a.dep - a.arr + gap
            if size > 0:
                on_p[a.platform].append(
                    m.NewFixedSizeIntervalVar(a.arr, size, f"fx_{a.train_id}")
                )

    # Fixed intervals for closures
    for c in inp.disruptions.closures:
        size = c.end - c.start
        if size > 0:
            on_p[c.platform_id].append(
                m.NewFixedSizeIntervalVar(c.start, size, f"cl_{c.platform_id}_{c.start}")
            )

    # Decision variables for movable trains
    terms: dict[str, list] = {"unassigned": [], "delay": [], "changes": []}

    for t in movable:
        e = t.arr + arr_d[t.id]                          # earliest arrival
        stay = (t.dep - t.arr) + dep_d[t.id]             # dwell + departure delay
        pi = 5 - t.priority                              # priority weight (SF=4, GDS=1)

        hold = m.NewIntVar(0, max_hold, f"h_{t.id}")
        start = m.NewIntVar(e, e + max_hold, f"s_{t.id}")
        m.Add(start == e + hold)

        xs: dict[str, Any] = {}
        for p in candidates(t, st):
            x = m.NewBoolVar(f"x_{t.id}_{p}")
            xs[p] = x
            on_p[p].append(
                m.NewOptionalFixedSizeIntervalVar(
                    start, stay + gap, x, f"iv_{t.id}_{p}"
                )
            )

        u = m.NewBoolVar(f"u_{t.id}")
        m.AddExactlyOne(list(xs.values()) + [u])

        terms["unassigned"].append(pi * u)
        terms["delay"].append(pi * hold)

        # Change indicator: 1 if moved from base platform
        if base.get(t.id) in xs:
            terms["changes"].append(1 - xs[base[t.id]])
        else:
            terms["changes"].append(1)

        dec[t.id] = (t, xs, u, hold, e, stay)

    # No-overlap constraints per platform
    for ivs in on_p.values():
        if len(ivs) > 1:
            m.AddNoOverlap(ivs)

    # Sequential lexicographic solve
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    stages: list[dict[str, Any]] = []

    wall = 0.0
    for name in ORDER[method]:
        if not terms[name]:                              # nothing movable: level is trivially 0
            stages.append({"level": name, "value": 0, "status": "OPTIMAL"})
            continue
        obj = sum(terms[name])
        m.Minimize(obj)
        solver.parameters.max_time_in_seconds = STAGE_SECONDS
        status = solver.Solve(m)
        wall += solver.WallTime()

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return Revision.solver_failed(method, solver.StatusName(status), stages)

        best = int(round(solver.ObjectiveValue()))
        stages.append({
            "level": name,
            "value": best,
            "status": solver.StatusName(status),
        })

        # Freeze this level
        m.Add(obj <= best)
        m.ClearHints()

        # Warm-start next level
        for _, xs, _, hold, _, _ in dec.values():
            for x in xs.values():
                m.AddHint(x, solver.Value(x))
            m.AddHint(hold, solver.Value(hold))

    # Build assignments from the solution
    out = list(frozen)
    for tid, (t, xs, u, hold, e, stay) in dec.items():
        if solver.Value(u):
            out.append(Assignment.unassigned(tid, reason_code="NO_SLOT_WITHIN_MAX_HOLD"))
            continue
        p = next(p for p, x in xs.items() if solver.Value(x))
        h = solver.Value(hold)
        out.append(Assignment.assigned(tid, p, e + h, e + h + stay, h))

    proven = all(s["status"] == "OPTIMAL" for s in stages)
    return Revision(
        method=method,
        assignments=out,
        solver_status="OPTIMAL" if proven else "FEASIBLE",
        stages=stages,
        solve_ms=int(wall * 1000),
    )


def plan(inp: PlanInput, method: str) -> Revision:
    """Two-stage affected-set replanning (SPEC §44).

    Stage 1: only affected trains may move. Stage 2 (only if stage 1 fails or leaves a
    train UNASSIGNED): every movable train may move, and the revision says so.
    With no pending disruptions (first assignment) every train is movable from the start.
    """
    A = plan_affected(inp)
    rev = plan_cpsat(inp, method, movable_ids=A)
    if A is not None and (rev.failed or rev.unassigned_count()):
        stage1 = rev
        rev = plan_cpsat(inp, method, movable_ids=None)
        rev.widened = True
        rev.widened_reason = (f"No placement for {stage1.unassigned_count() or 'some'} train(s) "
                              f"using affected trains only; widened to all movable trains")
    rev.affected = sorted(A or [])
    return rev
