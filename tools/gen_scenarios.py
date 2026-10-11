"""Seeded scenario generators (SPEC §20.3, §21).

- generate(seed, n): n disruption scenarios on data/timetable_peak.json for the benchmark
  (1–3 delays of 5–45 min, 0–2 closures of 30–120 min), deterministic for a seed.
- scenario_strategy(): Hypothesis strategy of small random stations, timetables, applied plans,
  clocks and disruptions for the property tests. Generated inputs are always *operationally
  possible*: the applied plan is valid, delays respect the train's state at `now`, and no closure
  starts under a train that is already at its platform (that is OPERATOR_ACTION_REQUIRED, §6).

    python tools/gen_scenarios.py --seed 7 --n 20      # prints the benchmark scenarios as JSON
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
from dataclasses import dataclass
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from railflow.models import (Assignment, Closure, Delay, Disruptions, Platform, PlanInput, Revision,  # noqa: E402
                             Station, Timetable, TimetableIn, Train)
from railflow.timeutil import to_hhmm  # noqa: E402


@dataclass
class Scenario:
    station: Station
    timetable: Timetable
    applied: list[Assignment]
    disruptions: Disruptions
    now: int
    name: str = ""

    @property
    def plan_input(self) -> PlanInput:
        return PlanInput(station=self.station, timetable=self.timetable, applied=self.applied,
                         disruptions=self.disruptions, now=self.now)

    @property
    def applied_revision(self) -> Revision:
        return Revision(method="applied", assignments=self.applied)


def load_peak() -> tuple[Station, Timetable]:
    st = Station.model_validate_json((ROOT / "data" / "station_shivneri.json").read_text(encoding="utf-8"))
    tt = TimetableIn.model_validate_json((ROOT / "data" / "timetable_peak.json").read_text(encoding="utf-8")).to_timetable()
    return st, tt


def scheduled_applied(tt: Timetable) -> list[Assignment]:
    return [Assignment.assigned(t.id, t.platform, t.arr, t.dep) if t.platform else Assignment.unassigned(t.id, None)
            for t in tt.trains]


def _possible(rng: random.Random, tt: Timetable, applied: list[Assignment], now: int, gap: int,
              n_delays: int, n_closures: int, dmin: int, dmax: int, cmin: int, cmax: int,
              platforms: list[str]) -> Disruptions:
    slot = {a.train_id: a for a in applied if a.status == "ASSIGNED"}
    delays: list[Delay] = []
    dep_extra: dict[str, int] = {}
    pool = [t for t in tt.trains if t.id in slot and slot[t.id].dep > now]
    rng.shuffle(pool)
    for t in pool[:n_delays]:
        a = slot[t.id]
        kind = "departure" if a.arr <= now else rng.choice(["arrival", "arrival", "departure"])
        m = rng.randint(dmin, dmax)
        delays.append(Delay(train_id=t.id, minutes=m, kind=kind))
        if kind == "departure":
            dep_extra[t.id] = m
    at_pf = [(a.platform, a.arr, a.dep + dep_extra.get(a.train_id, 0)) for a in slot.values() if a.arr <= now]
    closures: list[Closure] = []
    tries = 0
    while len(closures) < n_closures and tries < 50:
        tries += 1
        p = rng.choice(platforms)
        s = rng.randint(now, now + 150) // 5 * 5
        e = min(1439, s + rng.randint(cmin, cmax) // 5 * 5)
        if e <= s or any(q == p and a < e and s < d + gap for q, a, d in at_pf):
            continue
        if any(c.platform_id == p and c.start < e and s < c.end for c in closures):
            continue
        closures.append(Closure(platform_id=p, start=s, end=e))
    return Disruptions(delays=delays, closures=closures)


def generate(seed: int = 7, n: int = 20) -> list[Scenario]:
    """Benchmark scenarios on the peak timetable (§21)."""
    st, tt = load_peak()
    applied = scheduled_applied(tt)
    rng = random.Random(seed)
    out = []
    for i in range(n):
        now = rng.randint(12 * 60 + 30, 15 * 60) // 5 * 5
        dis = _possible(rng, tt, applied, now, st.min_gap, rng.randint(1, 3), rng.randint(0, 2), 5, 45, 30, 120,
                        [p.id for p in st.platforms if p.id != "P5"])
        out.append(Scenario(st, tt, applied, dis, now, name=f"B{i + 1:02d}"))
    return out


# ─────────────────────────── Hypothesis strategy ───────────────────────────

TYPES = [("SF", 26, None, 1), ("MEX", 24, None, 2), ("PAS", 18, None, 3), ("MEMU", 12, None, 3), ("GDS", None, 40, 4)]


def random_case(seed: int) -> Optional[Scenario]:
    """One small random case; None if the generated applied plan leaves nothing to test."""
    from railflow.planner_greedy import plan_greedy

    rng = random.Random(seed)
    n_pf = rng.randint(2, 5)
    plats = []
    for k in range(1, n_pf + 1):
        plats.append(Platform(id=f"P{k}", name=f"PF {k}", length_coaches=rng.choice([12, 18, 24, 26]),
                              goods_loop_wagons=rng.choice([0, 0, 60]), aliases=[str(k), f"pf {k}"]))
    st = Station(id="TST", code="TST", name="Test Junction", min_gap=rng.randint(0, 8),
                 max_hold=rng.randint(10, 60), platforms=plats)
    trains = []
    for i in range(rng.randint(3, 14)):
        typ, coaches, wagons, prio = rng.choice(TYPES)
        arr = rng.randint(600, 900)
        dwell = rng.randint(2, 20)
        fits = [p.id for p in plats if (wagons or 0) <= p.goods_loop_wagons and (coaches or 0) <= p.length_coaches]
        if typ == "GDS":
            fits = [p.id for p in plats if p.goods_loop_wagons >= (wagons or 0)]
        if not fits:
            continue
        allowed = sorted(rng.sample(fits, rng.randint(1, len(fits)))) if rng.random() < 0.6 else []
        req = rng.choice(allowed or fits) if rng.random() < 0.15 else None
        if req and allowed and req not in allowed:
            req = None
        trains.append(Train(id=f"{90000 + i}", name=f"T{i}", type=typ, arr=arr, dep=arr + dwell,
                            platform=rng.choice(allowed or fits), required_platform=req, allowed_platforms=allowed,
                            coaches=coaches, wagons=wagons, priority=prio))
    if len(trains) < 2:
        return None
    tt = Timetable(station="TST", trains=trains)
    first = plan_greedy(PlanInput(station=st, timetable=tt, now=0), movable_ids=None)
    applied = [a if a.status == "ASSIGNED" else Assignment.unassigned(a.train_id, a.reason_code) for a in first.assignments]
    now = rng.randint(580, 900)
    dis = _possible(rng, tt, applied, now, st.min_gap, rng.randint(0, 3), rng.randint(0, 2), 1, 45, 10, 120,
                    [p.id for p in plats])
    return Scenario(st, tt, applied, dis, now, name=f"H{seed}")


def scenario_strategy():
    from hypothesis import assume, strategies as hs

    @hs.composite
    def _s(draw):
        sc = random_case(draw(hs.integers(min_value=0, max_value=2 ** 31 - 1)))
        assume(sc is not None)
        return sc
    return _s()


def as_json(sc: Scenario) -> dict:
    return {"name": sc.name, "now": to_hhmm(sc.now),
            "delays": [d.model_dump() for d in sc.disruptions.delays],
            "closures": [{"platform_id": c.platform_id, "start": to_hhmm(c.start), "end": to_hhmm(c.end)}
                         for c in sc.disruptions.closures]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    print(json.dumps([as_json(s) for s in generate(a.seed, a.n)], indent=1))
