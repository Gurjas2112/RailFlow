"""SPEC §44 — stage-1 revisions leave every train outside the affected set exactly where it was."""
import pytest

from railflow.models import Closure, Delay, Disruptions, PlanInput
from railflow.planner_cpsat import plan
from railflow.planner_greedy import plan as plan_greedy
from railflow.state import affected_set, plan_affected
from railflow.timeutil import to_min

CASES = {
    "S2": (Disruptions(delays=[Delay(train_id="11209", minutes=30)],
                       closures=[Closure(platform_id="P3", start=to_min("14:00"), end=to_min("15:30"))]), "13:50",
           {"11209", "51219", "11217"}),
    "S8": (Disruptions(delays=[Delay(train_id="51218", minutes=25, kind="departure")],
                       closures=[Closure(platform_id="P3", start=to_min("14:30"), end=to_min("15:10"))]), "14:10",
           {"51218", "51215", "51219", "11217"}),
}


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("method", ["cpsat_min_delay", "cpsat_min_changes", "greedy"])
def test_outside_affected_unchanged(station, tt_normal, name, method):
    dis, now, expect = CASES[name]
    inp = PlanInput(station=station, timetable=tt_normal, disruptions=dis, now=to_min(now))
    assert plan_affected(inp) == expect
    rev = plan_greedy(inp) if method == "greedy" else plan(inp, method)
    assert not rev.widened and set(rev.affected) == expect
    before = inp.applied_plan()
    for a in rev.assignments:
        if a.train_id not in expect:
            b = before[a.train_id]
            assert (a.platform, a.arr, a.dep) == (b.platform, b.arr, b.dep), a.train_id


def test_affected_set_is_a_fixed_point(station, tt_normal):
    inp = PlanInput(station=station, timetable=tt_normal)
    dis = CASES["S8"][0]
    first = affected_set(inp.applied_plan().values(), dis, station.min_gap)
    assert affected_set(inp.applied_plan().values(), dis, station.min_gap) == first


def test_no_disruption_means_everything_movable(station, tt_normal):
    assert plan_affected(PlanInput(station=station, timetable=tt_normal)) is None
