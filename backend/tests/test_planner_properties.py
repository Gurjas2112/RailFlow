"""SPEC §20.3 — property-based tests: every planner output validates; every injected fault is caught."""
from hypothesis import HealthCheck, given, settings

from railflow.fault import inject_fault
from railflow.planner_cpsat import plan as plan_cpsat
from railflow.planner_greedy import plan as plan_greedy
from railflow.validator import validate
from tools.gen_scenarios import generate, scenario_strategy

SETTINGS = dict(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])


def plan_all(inp):
    return [plan_cpsat(inp, "cpsat_min_delay"), plan_cpsat(inp, "cpsat_min_changes"), plan_greedy(inp)]


@settings(**SETTINGS)
@given(scenario_strategy())
def test_every_planner_output_validates(sc):
    for rev in plan_all(sc.plan_input):
        if rev.failed:
            continue                                    # a timeout is reported as SOLVER_FAILED, never shown valid
        rep = validate(sc.station, sc.timetable, sc.disruptions, rev, sc.applied_revision, sc.now)
        assert rep.valid, (rev.method, rep.conflicts)


@settings(**SETTINGS)
@given(scenario_strategy())
def test_validator_catches_every_injected_fault(sc):
    rev = inject_fault(plan_cpsat(sc.plan_input, "cpsat_min_delay"), sc.now, sc.station.min_gap)
    if rev.fault_injected:
        assert not validate(sc.station, sc.timetable, sc.disruptions, rev, sc.applied_revision, sc.now).valid


def test_cpsat_never_worse_than_greedy_on_weighted_delay():
    from railflow.metrics import compute_metrics
    for sc in generate(seed=7, n=20):
        inp = sc.plan_input
        g, c = plan_greedy(inp), plan_cpsat(inp, "cpsat_min_delay")
        mg, mc = compute_metrics(g, inp), compute_metrics(c, inp)
        pg = sum(5 - inp.timetable.by_id()[a.train_id].priority for a in g.assignments if a.status == "UNASSIGNED")
        pc = sum(5 - inp.timetable.by_id()[a.train_id].priority for a in c.assignments if a.status == "UNASSIGNED")
        assert pc <= pg, sc.name
        if pc == pg and c.solver_status == "OPTIMAL" and c.affected == g.affected and not (c.widened or g.widened):
            assert mc.weighted_delay <= mg.weighted_delay, sc.name
