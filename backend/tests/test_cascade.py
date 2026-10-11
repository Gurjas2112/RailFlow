"""SPEC §45 — S8 cascade: properties, not exact minutes (plus the reason-card sentences)."""
from railflow.models import Closure, Delay, Disruptions, PlanInput
from railflow.planner_cpsat import plan
from railflow.reasons import classify_and_reason
from railflow.timeutil import to_min
from railflow.validator import validate


def _s8(station, tt):
    dis = Disruptions(delays=[Delay(train_id="51218", minutes=25, kind="departure")],
                      closures=[Closure(platform_id="P3", start=to_min("14:30"), end=to_min("15:10"))])
    return PlanInput(station=station, timetable=tt, disruptions=dis, now=to_min("14:10"))


def test_s8_cascade_chain(station, tt_normal):
    inp = _s8(station, tt_normal)
    for method in ("cpsat_min_delay", "cpsat_min_changes"):
        rev = plan(inp, method)
        assert set(rev.affected) == {"51218", "51215", "51219", "11217"}
        assert validate(station, tt_normal, inp.disruptions, rev, inp.applied_revision(), inp.now).valid
        changes = {c.train_id: c for c in classify_and_reason(rev, inp)}
        others = [c for t, c in changes.items() if t not in rev.affected]
        assert len(others) == 26 and all(c.cls in ("UNCHANGED", "FROZEN") and c.after == c.before for c in others)
        c15 = changes["51215"]
        assert c15.cls == "HELD" and c15.hold == 15 and c15.caused_by == ["51218"]
        assert any(p.code == "HELD_OCCUPIED" and p.params["train"] == "51218" for p in c15.parts)
        assert changes["51218"].cls == "FROZEN" and changes["51218"].parts[0].code == "FROZEN_DEPARTURE_DELAY"
        assert changes["51219"].caused_by[0].startswith("closure:P3")


def test_reason_sentences_name_concrete_blockers(station, tt_normal):
    inp = _s8(station, tt_normal)
    text = {c.train_id: c.text for c in classify_and_reason(plan(inp, "cpsat_min_delay"), inp)}
    assert text["51215"] == "held 15 min: P2 occupied by 51218 until 14:45 + 5 min gap"
    assert "P3 closed 14:30–15:10" in text["11217"]
