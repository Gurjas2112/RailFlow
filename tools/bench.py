"""Benchmark (SPEC §21): greedy vs CP-SAT min-delay vs CP-SAT min-changes on seeded scenarios.

    python tools/bench.py [--seed 7] [--n 20]        # → results/bench.md

"Valid plans" is the independent validator speaking; the delay column is CP-SAT's advantage measured.
"""
from __future__ import annotations

import argparse
import pathlib
import platform
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from gen_scenarios import generate  # noqa: E402
from railflow.metrics import compute_metrics  # noqa: E402
from railflow.planner_cpsat import plan as plan_cpsat  # noqa: E402
from railflow.planner_greedy import plan as plan_greedy  # noqa: E402
from railflow.validator import validate  # noqa: E402

METHODS = [("Greedy", lambda inp: plan_greedy(inp)),
           ("CP-SAT min-delay", lambda inp: plan_cpsat(inp, "cpsat_min_delay")),
           ("CP-SAT min-changes", lambda inp: plan_cpsat(inp, "cpsat_min_changes"))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "results" / "bench.md"))
    a = ap.parse_args()
    scenarios = generate(a.seed, a.n)
    rows, detail = [], []
    for name, fn in METHODS:
        valid = wd = changes = unassigned = optimal = widened = 0
        times = []
        for sc in scenarios:
            inp = sc.plan_input
            t0 = time.perf_counter()
            rev = fn(inp)
            times.append((time.perf_counter() - t0) * 1000)
            rep = validate(sc.station, sc.timetable, sc.disruptions, rev, sc.applied_revision, sc.now)
            m = compute_metrics(rev, inp)
            valid += rep.valid
            wd += m.weighted_delay
            changes += m.platform_changes
            unassigned += m.unassigned
            optimal += rev.solver_status == "OPTIMAL"
            widened += rev.widened
            detail.append((sc.name, name, rep.valid, m.weighted_delay, m.platform_changes, m.unassigned, rev.solver_status))
        rows.append((name, valid, wd, changes, unassigned, statistics.median(times), optimal, widened))

    n = len(scenarios)
    out = [
        "# Benchmark (measured)", "",
        f"`python tools/bench.py --seed {a.seed} --n {n}` on `data/timetable_peak.json` (36 trains): "
        "1–3 delays of 5–45 min and 0–2 closures of 30–120 min per scenario, applied plan = scheduled platforms. "
        f"Machine: {platform.processor() or platform.machine()} · Python {platform.python_version()}. "
        "Solve time includes the two-stage affected-set solve and, when needed, the widened stage.", "",
        "| Method | Valid plans | Total weighted delay (sum) | Platform changes (sum) | Unassigned (sum) | Median solve time | OPTIMAL proven | Widened |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, valid, wd, ch, un, med, opt, wid in rows:
        out.append(f"| {name} | {valid}/{n} | {wd} | {ch} | {un} | {med:.0f} ms | "
                   f"{'—' if name == 'Greedy' else f'{opt}/{n}'} | {wid}/{n} |")
    out += ["", "Per scenario:", "", "| Scenario | Method | Valid | Weighted delay | Changes | Unassigned | Status |", "|---|---|---|---|---|---|---|"]
    out += [f"| {s} | {m} | {'VALID' if v else 'NOT VALID'} | {w} | {c} | {u} | {st} |" for s, m, v, w, c, u, st in
            sorted(detail)]
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:4 + len(rows) + 2]))


if __name__ == "__main__":
    main()
