"""SPEC §43 — a train at its platform leaving late: frozen platform and arrival, longer stay."""
from railflow.models import Delay, Disruptions, PlanInput
from railflow.planner_cpsat import plan
from railflow.planner_greedy import plan as plan_greedy
from railflow.state import frozen_and_movable
from railflow.timeutil import to_min
from railflow.validator import validate


def _inp(station, tt):
    return PlanInput(station=station, timetable=tt, now=to_min("14:10"),
                     disruptions=Disruptions(delays=[Delay(train_id="51218", minutes=20, kind="departure")]))


def test_frozen_train_keeps_platform_and_arrival(station, tt_normal):
    inp = _inp(station, tt_normal)
    frozen, _ = frozen_and_movable(inp)
    f = {a.train_id: a for a in frozen}["51218"]
    assert (f.platform, f.arr, f.dep) == ("P2", to_min("14:00"), to_min("14:40"))
    for rev in (plan(inp, "cpsat_min_delay"), plan_greedy(inp)):
        a = rev.by_train()["51218"]
        assert (a.platform, a.arr, a.dep) == ("P2", to_min("14:00"), to_min("14:40"))
        assert validate(station, tt_normal, inp.disruptions, rev, inp.applied_revision(), inp.now).valid


def test_validator_rejects_moving_a_frozen_train(station, tt_normal):
    inp = _inp(station, tt_normal)
    rev = plan(inp, "cpsat_min_delay")
    i = next(i for i, a in enumerate(rev.assignments) if a.train_id == "51218")
    rev.assignments[i] = rev.assignments[i].model_copy(update={"platform": "P4"})
    codes = [c.code for c in validate(station, tt_normal, inp.disruptions, rev, inp.applied_revision(), inp.now).conflicts]
    assert "FROZEN_CHANGED" in codes
