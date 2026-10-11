"""SPEC §20.1 — one test per validator rule on hand-built micro-timetables, plus sweep and boundaries."""
from railflow.models import (Assignment, Closure, Delay, Disruptions, Platform, Revision, Station, Timetable,
                             Train)
from railflow.validator import validate

ST = Station(id="TST", name="Test", min_gap=5, max_hold=30, platforms=[
    Platform(id="P1", name="PF 1", length_coaches=26),
    Platform(id="P2", name="PF 2", length_coaches=12),
    Platform(id="P3", name="PF 3", length_coaches=24, goods_loop_wagons=60),
])


def T(tid, arr, dep, **kw):
    kw.setdefault("type", "PAS")
    kw.setdefault("coaches", 12 if kw["type"] != "GDS" else None)
    kw.setdefault("priority", 3)
    return Train(id=tid, arr=arr, dep=dep, **kw)


def A(tid, pf, arr, dep, hold=0):
    return Assignment.assigned(tid, pf, arr, dep, hold)


def run(trains, assignments, dis=None, applied=None, now=0):
    return validate(ST, Timetable(trains=trains), dis or Disruptions(), Revision(method="t", assignments=assignments),
                    Revision(method="applied", assignments=applied) if applied else None, now)


def codes(rep):
    return sorted(c.code for c in rep.conflicts)


def test_valid_plan():
    rep = run([T("10001", 600, 610), T("10002", 620, 630)], [A("10001", "P1", 600, 610), A("10002", "P1", 620, 630)])
    assert rep.valid and rep.checked_rules == [f"V{i}" for i in range(1, 11)]


def test_v1_missing_duplicate_unknown():
    tr = [T("10001", 600, 610), T("10002", 620, 630)]
    assert codes(run(tr, [A("10001", "P1", 600, 610)])) == ["MISSING_TRAIN"]
    assert "DUPLICATE_TRAIN" in codes(run(tr, [A("10001", "P1", 600, 610), A("10001", "P2", 600, 610),
                                                A("10002", "P1", 620, 630)]))
    assert codes(run(tr, [A("10001", "P1", 600, 610), A("10002", "P1", 620, 630), A("19999", "P2", 600, 610)])) \
        == ["UNKNOWN_TRAIN"]


def test_v2_unknown_platform():
    assert codes(run([T("10001", 600, 610)], [A("10001", "P9", 600, 610)])) == ["UNKNOWN_PLATFORM"]


def test_v3_required_and_allowed():
    assert codes(run([T("10001", 600, 610, required_platform="P2")], [A("10001", "P1", 600, 610)])) == ["REQUIRED_PLATFORM"]
    assert codes(run([T("10001", 600, 610, allowed_platforms=["P2"])], [A("10001", "P1", 600, 610)])) == ["NOT_ALLOWED_PLATFORM"]


def test_v4_dwell_and_bad_times():
    assert codes(run([T("10001", 600, 610)], [A("10001", "P1", 600, 612)])) == ["DWELL_CHANGED"]
    rep = run([T("10001", 600, 610)], [Assignment(train_id="10001", status="ASSIGNED", platform="P1", arr=610, dep=605)])
    assert "BAD_TIMES" in codes(rep)


def test_v4_departure_delay_lengthens_stay():
    dis = Disruptions(delays=[Delay(train_id="10001", minutes=7, kind="departure")])
    assert run([T("10001", 600, 610)], [A("10001", "P1", 600, 617)], dis).valid
    assert codes(run([T("10001", 600, 610)], [A("10001", "P1", 600, 610)], dis)) == ["DWELL_CHANGED"]


def test_v5_earlier_than_possible():
    dis = Disruptions(delays=[Delay(train_id="10001", minutes=10)])
    rep = run([T("10001", 600, 610)], [A("10001", "P1", 605, 615)], dis)
    assert codes(rep) == ["EARLIER_THAN_POSSIBLE"] and rep.conflicts[0].minutes == 5


def test_v6_hold_exceeded():
    rep = run([T("10001", 600, 610)], [A("10001", "P1", 631, 641, 31)])
    assert codes(rep) == ["HOLD_EXCEEDED"] and rep.conflicts[0].minutes == 31
    assert run([T("10001", 600, 610)], [A("10001", "P1", 630, 640, 30)]).valid


def test_v7_frozen_changed():
    tr = [T("10001", 600, 610)]
    applied = [A("10001", "P1", 600, 610)]
    assert codes(run(tr, [A("10001", "P2", 600, 610)], applied=applied, now=605)) == ["FROZEN_CHANGED"]
    assert "FROZEN_CHANGED" in codes(run(tr, [Assignment.unassigned("10001", "X")], applied=applied, now=605))
    assert run(tr, [A("10001", "P2", 600, 610)], applied=applied, now=599).valid


def test_v8_overlap_measures():
    rep = run([T("10001", 865, 880), T("10002", 875, 885)], [A("10001", "P1", 865, 880), A("10002", "P1", 875, 885)])
    (c,) = rep.conflicts
    assert (c.code, c.trains, c.stay_overlap_min, c.clearance_shortfall_min, c.reserved_overlap_min) == \
        ("OVERLAP", ["10001", "10002"], 5, None, 10)


def test_v8_gap_boundary():
    tr = [T("10001", 600, 610), T("10002", 615, 620)]
    assert run(tr, [A("10001", "P1", 600, 610), A("10002", "P1", 615, 620)]).valid          # exactly gap: valid
    tr = [T("10001", 600, 610), T("10002", 614, 620)]
    (c,) = run(tr, [A("10001", "P1", 600, 610), A("10002", "P1", 614, 620)]).conflicts
    assert (c.code, c.clearance_shortfall_min, c.reserved_overlap_min, c.stay_overlap_min) == ("GAP_VIOLATION", 1, 1, 0)


def test_v8_reports_every_pair_not_just_adjacent():
    tr = [T("10001", 600, 660), T("10002", 610, 615), T("10003", 630, 635)]
    rep = run(tr, [A("10001", "P1", 600, 660), A("10002", "P1", 610, 615), A("10003", "P1", 630, 635)])
    pairs = sorted(tuple(c.trains) for c in rep.conflicts)
    assert ("10001", "10002") in pairs and ("10001", "10003") in pairs


def test_v9_closure_and_gap_before_closure():
    dis = Disruptions(closures=[Closure(platform_id="P1", start=620, end=650)])
    assert codes(run([T("10001", 600, 616)], [A("10001", "P1", 600, 616)], dis)) == ["CLOSURE_VIOLATION"]
    assert run([T("10001", 600, 615)], [A("10001", "P1", 600, 615)], dis).valid       # leaves gap before closure
    assert run([T("10001", 650, 660)], [A("10001", "P1", 650, 660)], dis).valid       # arrives the minute it ends


def test_v10_capacity_passenger_and_goods():
    long = T("10001", 600, 610, coaches=24)
    assert codes(run([long], [A("10001", "P2", 600, 610)])) == ["CAPACITY_EXCEEDED"]
    goods = T("10002", 600, 610, type="GDS", wagons=58, priority=4)
    assert run([goods], [A("10002", "P3", 600, 610)]).valid
    assert codes(run([goods], [A("10002", "P1", 600, 610)])) == ["CAPACITY_EXCEEDED"]   # wagons never vs coaches


def test_unassigned_needs_reason():
    assert codes(run([T("10001", 600, 610)], [Assignment.unassigned("10001", None)])) == ["UNASSIGNED_WITHOUT_REASON"]
    assert run([T("10001", 600, 610)], [Assignment.unassigned("10001", "NO_SLOT_WITHIN_MAX_HOLD")]).valid
