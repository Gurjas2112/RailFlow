"""SPEC §47.2 — arrival and departure delays are accounted separately everywhere."""
from railflow.models import Closure, Delay, Disruptions, PlanInput
from railflow.planner_cpsat import plan
from railflow.planner_greedy import plan as plan_greedy
from railflow.proposals import validate_proposals
from railflow.timeutil import to_min
from railflow.validator import validate


def _inp(station, tt, delays, now, closures=()):
    return PlanInput(station=station, timetable=tt, disruptions=Disruptions(delays=delays, closures=list(closures)), now=now)


def _ok(inp, rev):
    return validate(inp.station, inp.timetable, inp.disruptions, rev, inp.applied_revision(), inp.now)


def test_future_train_arrival_delay(station, tt_normal):
    inp = _inp(station, tt_normal, [Delay(train_id="11225", minutes=10)], to_min("13:00"))
    a = plan(inp, "cpsat_min_delay").by_train()["11225"]
    assert a.arr >= to_min("15:50") and a.dep - a.arr == 12              # dwell kept, arrival shifted
    assert _ok(inp, plan(inp, "cpsat_min_delay")).valid


def test_at_platform_departure_delay(station, tt_normal):
    inp = _inp(station, tt_normal, [Delay(train_id="51218", minutes=25, kind="departure")], to_min("14:10"))
    rev = plan(inp, "cpsat_min_delay")
    a = rev.by_train()["51218"]
    assert (a.platform, a.arr, a.dep) == ("P2", to_min("14:00"), to_min("14:45"))   # frozen, stay lengthened
    assert _ok(inp, rev).valid


def test_both_kinds_on_one_train(station, tt_normal):
    inp = _inp(station, tt_normal, [Delay(train_id="11225", minutes=10), Delay(train_id="11225", minutes=5, kind="departure")],
               to_min("13:00"))
    a = plan(inp, "cpsat_min_delay").by_train()["11225"]
    assert a.arr - a.hold == to_min("15:50") and a.dep - a.arr == 12 + 5
    assert _ok(inp, plan(inp, "cpsat_min_delay")).valid and _ok(inp, plan_greedy(inp)).valid


def test_delay_to_departed_train_rejected(station, tt_normal):
    ev = [{"type": "delay", "train_id": "11101", "minutes": 10, "kind": "departure", "source": "11101 late 10 min"}]
    ok, rej, _ = validate_proposals(ev, [], "11101 late 10 min", station, tt_normal, to_min("13:00"))
    assert not ok and rej[0].reason.code == "ALREADY_DEPARTED"


def test_departure_delay_propagates_to_next_train(station, tt_normal):
    inp = _inp(station, tt_normal, [Delay(train_id="51218", minutes=25, kind="departure")], to_min("14:10"),
               [Closure(platform_id="P3", start=to_min("14:30"), end=to_min("15:10"))])
    a = plan(inp, "cpsat_min_delay").by_train()["51215"]
    assert a.arr >= to_min("14:45") + station.min_gap or a.platform != "P2"


def test_hold_above_max_hold_is_v6(station, tt_normal):
    inp = _inp(station, tt_normal, [], to_min("12:00"))
    rev = plan(inp, "cpsat_min_delay")
    i = next(i for i, a in enumerate(rev.assignments) if a.train_id == "11225")
    a = rev.assignments[i]
    over = station.max_hold + 1
    rev.assignments[i] = a.model_copy(update={"arr": a.arr + over, "dep": a.dep + over, "hold": over})
    assert "HOLD_EXCEEDED" in [c.code for c in _ok(inp, rev).conflicts]
