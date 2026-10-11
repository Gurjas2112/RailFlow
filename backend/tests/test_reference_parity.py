"""SPEC §47.8 — the product reproduces tools/reference/REFERENCE_RUN.md on the shipped data.

Validator conflicts, affected sets, recovery status and objective values must equal the reference;
exact platform choices may differ only where objective values tie. The reference is never imported.
"""
import pytest

from railflow.fault import inject_fault
from railflow.metrics import compute_metrics
from railflow.models import Closure, Delay, Disruptions, PlanInput, recovery_status
from railflow.planner_cpsat import plan, plan_cpsat
from railflow.planner_greedy import plan as plan_greedy
from railflow.state import plan_affected
from railflow.timeutil import to_min
from railflow.validator import validate


def measures(rep):
    return sorted((c.code, c.platform, tuple(c.trains), c.stay_overlap_min, c.clearance_shortfall_min,
                   c.reserved_overlap_min) for c in rep.conflicts)


def test_s3_scheduled_conflicts(station, tt_conflicts):
    inp = PlanInput(station=station, timetable=tt_conflicts)
    rep = validate(station, tt_conflicts, Disruptions(), inp.applied_revision(), None, 0)
    assert measures(rep) == sorted([
        ("GAP_VIOLATION", "P1", ("11214", "11216"), 0, 2, 2),
        ("GAP_VIOLATION", "P2", ("51218", "51219"), 0, 3, 3),
        ("OVERLAP", "P4", ("51214", "51215"), 5, None, 10),
    ])


def test_conflict_free_sheet(station, tt_normal):
    inp = PlanInput(station=station, timetable=tt_normal)
    assert validate(station, tt_normal, Disruptions(), inp.applied_revision(), None, 0).valid


def check(inp, rev, moves, hold, weighted, unassigned=0):
    rep = validate(inp.station, inp.timetable, inp.disruptions, rev, inp.applied_revision(), inp.now)
    assert rep.valid, rep.conflicts
    m = compute_metrics(rev, inp)
    assert (m.platform_changes, m.total_hold_min, m.weighted_delay, m.unassigned) == (moves, hold, weighted, unassigned)
    assert m.moved_outside_affected == 0
    assert recovery_status(rev) == "FULLY_ASSIGNED"
    return m


def test_s1_assign(station, tt_normal):
    inp = PlanInput(station=station, timetable=tt_normal, now=to_min("12:00"))
    assert plan_affected(inp) is None                         # nothing disrupted: first assignment
    for method in ("cpsat_min_delay", "cpsat_min_changes"):
        rev = plan(inp, method)
        check(inp, rev, 0, 0, 0)
        assert rev.solver_status == "OPTIMAL"
    check(inp, plan_greedy(inp), 0, 0, 0)


@pytest.fixture(scope="module")
def s2(station, tt_normal):
    dis = Disruptions(delays=[Delay(train_id="11209", minutes=30)],
                      closures=[Closure(platform_id="P3", start=to_min("14:00"), end=to_min("15:30"))])
    return PlanInput(station=station, timetable=tt_normal, disruptions=dis, now=to_min("13:50"))


def test_s2_affected(s2):
    assert plan_affected(s2) == {"11209", "51219", "11217"}


@pytest.mark.parametrize("method", ["cpsat_min_delay", "cpsat_min_changes", "greedy"])
def test_s2_all_methods_agree(s2, method):
    rev = plan_greedy(s2) if method == "greedy" else plan(s2, method)
    check(s2, rev, 3, 16, 45)
    by = rev.by_train()
    assert (by["11209"].platform, by["11209"].arr, by["11209"].hold) == ("P4", to_min("14:45"), 13)
    assert (by["51219"].platform, by["51219"].arr, by["51219"].hold) == ("P2", to_min("14:25"), 3)
    assert (by["11217"].platform, by["11217"].arr, by["11217"].hold) == ("P1", to_min("14:50"), 0)


@pytest.fixture(scope="module")
def s8(station, tt_normal):
    dis = Disruptions(delays=[Delay(train_id="51218", minutes=25, kind="departure")],
                      closures=[Closure(platform_id="P3", start=to_min("14:30"), end=to_min("15:10"))])
    return PlanInput(station=station, timetable=tt_normal, disruptions=dis, now=to_min("14:10"))


def test_s8_affected(s8):
    assert plan_affected(s8) == {"51218", "51215", "51219", "11217"}


@pytest.mark.parametrize("method,moves,hold,weighted", [
    ("cpsat_min_delay", 2, 38, 76),
    ("cpsat_min_changes", 1, 58, 136),
])
def test_s8_cpsat(s8, method, moves, hold, weighted):
    rev = plan(s8, method)
    check(s8, rev, moves, hold, weighted)
    assert rev.solver_status == "OPTIMAL" and not rev.widened


def test_s8_greedy(s8):
    check(s8, plan_greedy(s8), 3, 40, 85)


def test_s5_fault_on_s8_min_delay(s8):
    rev = inject_fault(plan(s8, "cpsat_min_delay"), s8.now, s8.station.min_gap)
    assert rev.fault_injected
    rep = validate(s8.station, s8.timetable, s8.disruptions, rev, s8.applied_revision(), s8.now)
    assert not rep.valid
    assert measures(rep) == [("OVERLAP", "P1", ("12222", "51215"), 7, None, 12)]


def test_lexicographic_goods_held_not_unassigned(station, tt_normal):
    """§47.5: close PF 4, the only goods PF, 12:30–13:00 → GDS-4105 held 20, 0 unassigned."""
    dis = Disruptions(closures=[Closure(platform_id="P4", start=to_min("12:30"), end=to_min("13:00"))])
    inp = PlanInput(station=station, timetable=tt_normal, disruptions=dis, now=0)
    rev = plan_cpsat(inp, "cpsat_min_delay", None)
    assert rev.unassigned_count() == 0
    assert rev.by_train()["GDS-4105"].hold == 20
    assert [s["value"] for s in rev.stages] == [0, 20, 0] and rev.solver_status == "OPTIMAL"
