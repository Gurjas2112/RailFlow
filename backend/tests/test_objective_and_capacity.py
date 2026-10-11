"""SPEC §47.3, §47.5, §47.6 — lexicographic hierarchy, goods capacity in wagons, separate recovery badge."""
from railflow.models import Assignment, Closure, Disruptions, PlanInput, Revision, recovery_status
from railflow.planner_cpsat import plan_cpsat
from railflow.state import candidates
from railflow.timeutil import to_min
from railflow.validator import validate


def test_objective_hierarchy_unassigned_first(station, tt_normal):
    """Closing PF 4 (only goods PF) 12:30–13:00: GDS-4105 waits 20 min rather than going unassigned."""
    dis = Disruptions(closures=[Closure(platform_id="P4", start=to_min("12:30"), end=to_min("13:00"))])
    inp = PlanInput(station=station, timetable=tt_normal, disruptions=dis)
    for method in ("cpsat_min_delay", "cpsat_min_changes"):
        rev = plan_cpsat(inp, method, None)
        assert rev.stages[0]["level"] == "unassigned" and rev.stages[0]["value"] == 0
        assert rev.by_train()["GDS-4105"].status == "ASSIGNED" and rev.by_train()["GDS-4105"].hold == 20


def test_capacity_candidates_in_wagons(station, tt_normal):
    trains = tt_normal.by_id()
    assert candidates(trains["GDS-4105"], station) == ["P4"]                 # 58 wagons ≤ 60 loop
    assert candidates(trains["12222"], station) == ["P1", "P2"]              # 26 coaches
    assert candidates(trains["61305"], station) == ["P5"]                    # MEMU bay


def test_goods_never_compared_with_coaches(station, tt_normal):
    gds = tt_normal.by_id()["GDS-4105"]
    big = gds.model_copy(update={"wagons": 61})
    assert candidates(big, station) == []                                    # does not fit the 60-wagon loop
    tt = tt_normal.model_copy(update={"trains": [big if t.id == gds.id else t for t in tt_normal.trains]})
    rev = PlanInput(station=station, timetable=tt).applied_revision()
    codes = [c.code for c in validate(station, tt, Disruptions(), rev, None, 0).conflicts]
    assert codes == ["CAPACITY_EXCEEDED"]


def test_recovery_badge_is_separate_from_validity():
    full = Revision(method="m", assignments=[Assignment.assigned("10001", "P1", 1, 2)])
    partial = Revision(method="m", assignments=[Assignment.unassigned("10001", "NO_SLOT_WITHIN_MAX_HOLD")])
    failed = Revision.solver_failed("m", "UNKNOWN")
    assert [recovery_status(r) for r in (full, partial, failed)] == ["FULLY_ASSIGNED", "PARTIAL", "SOLVER_FAILED"]


def test_partial_plan_can_still_be_valid(station):
    from railflow.scenario_store import load_timetable
    from railflow.planner_cpsat import plan
    tt = load_timetable("timetable_peak.json")
    dis = Disruptions(closures=[Closure(platform_id="P2", start=to_min("15:00"), end=to_min("16:30")),
                                Closure(platform_id="P4", start=to_min("15:00"), end=to_min("16:30"))])
    inp = PlanInput(station=station, timetable=tt, disruptions=dis, now=to_min("14:00"))
    rev = plan(inp, "cpsat_min_delay")
    rep = validate(station, tt, dis, rev, inp.applied_revision(), inp.now)
    assert rep.valid
    assert recovery_status(rev) == "PARTIAL" and rev.unassigned_count() > 0
    assert all(a.reason_code for a in rev.assignments if a.status == "UNASSIGNED")
