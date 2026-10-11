"""Independent validator — the product's spine (SPEC §9).

INDEPENDENCE RULE: this module imports only .models and the standard library.
A test (test_validator_independence.py) parses its imports and fails the build
if it ever imports planner code, state.py, or any other railflow module.

Algorithm: sweep line on each platform, not interval constraints.
Different author, different algorithm from the planner.

Rules V1-V10 — a revision is valid iff it has zero conflicts.
"""
from __future__ import annotations

from collections import defaultdict

from .models import (
    Conflict,
    Disruptions,
    Revision,
    Station,
    Timetable,
    ValidationReport,
)

VALIDATOR_VERSION = "v1.6"


def validate(
    station: Station,
    timetable: Timetable,
    disruptions: Disruptions,
    revision: Revision,
    applied: Revision | None,
    now: int,
) -> ValidationReport:
    """Validate a revision against the rules V1-V10.

    Returns a ValidationReport with valid=True iff there are zero conflicts.
    """
    C: list[Conflict] = []
    gap = station.min_gap
    plats = {p.id: p for p in station.platforms}
    orig = {t.id: t for t in timetable.trains}

    # Separate delay accounting (SPEC §47.2)
    arr_d: dict[str, int] = defaultdict(int)
    dep_d: dict[str, int] = defaultdict(int)
    for d in disruptions.delays:
        if d.kind == "departure":
            dep_d[d.train_id] += d.minutes
        else:
            arr_d[d.train_id] += d.minutes

    # ─── V1: every timetable train exactly once ───
    seen: dict[str, int] = defaultdict(int)
    for a in revision.assignments:
        seen[a.train_id] += 1
    for tid, n in seen.items():
        if tid not in orig:
            C.append(Conflict(code="UNKNOWN_TRAIN", trains=[tid]))
        elif n > 1:
            C.append(Conflict(code="DUPLICATE_TRAIN", trains=[tid]))
    for tid in orig.keys() - seen.keys():
        C.append(Conflict(code="MISSING_TRAIN", trains=[tid]))

    # Build the frozen set from the applied plan
    frozen: dict[str, object] = {}
    if applied is not None:
        for a in applied.assignments:
            if a.status == "ASSIGNED" and a.arr is not None and a.arr <= now:
                frozen[a.train_id] = a

    # Per-platform occupancy for V8 sweep
    occ: dict[str, list[tuple[int, int, str]]] = defaultdict(list)

    for a in revision.assignments:
        t = orig.get(a.train_id)
        if t is None:
            continue

        if a.status == "UNASSIGNED":
            # UNASSIGNED must carry a reason
            if not a.reason_code:
                C.append(Conflict(code="UNASSIGNED_WITHOUT_REASON", trains=[a.train_id]))
            # V7: frozen trains cannot be unassigned
            if a.train_id in frozen:
                C.append(Conflict(code="FROZEN_CHANGED", trains=[a.train_id]))
            continue

        # a.status == "ASSIGNED"
        p = plats.get(a.platform)  # type: ignore[arg-type]

        # ─── V2: platform exists ───
        if p is None:
            C.append(Conflict(code="UNKNOWN_PLATFORM", trains=[a.train_id], platform=a.platform))
            continue

        # ─── V3: required platform honoured; platform in allowed list ───
        if t.required_platform and a.platform != t.required_platform:
            C.append(Conflict(code="REQUIRED_PLATFORM", trains=[a.train_id], platform=a.platform))
        if t.allowed_platforms and a.platform not in t.allowed_platforms:
            C.append(Conflict(code="NOT_ALLOWED_PLATFORM", trains=[a.train_id], platform=a.platform))

        # ─── V10: capacity check (own, not from allowed list) ───
        if t.type == "GDS":
            if (t.wagons or 0) > p.goods_loop_wagons:
                C.append(Conflict(code="CAPACITY_EXCEEDED", trains=[a.train_id], platform=a.platform, minutes=0))
        elif (t.coaches or 0) > p.length_coaches:
            C.append(Conflict(code="CAPACITY_EXCEEDED", trains=[a.train_id], platform=a.platform, minutes=0))

        # ─── V4: dwell preservation + departure delay ───
        if a.arr is None or a.dep is None:
            C.append(Conflict(code="BAD_TIMES", trains=[a.train_id]))
            continue
        if a.dep <= a.arr:
            C.append(Conflict(code="BAD_TIMES", trains=[a.train_id]))
        expected_stay = (t.dep - t.arr) + dep_d[t.id]
        if a.dep - a.arr != expected_stay:
            C.append(Conflict(code="DWELL_CHANGED", trains=[a.train_id]))

        # ─── V5: arrival not earlier than possible ───
        earliest = t.arr + arr_d[t.id]
        if a.arr < earliest:
            C.append(Conflict(code="EARLIER_THAN_POSSIBLE", trains=[a.train_id], minutes=earliest - a.arr))

        # ─── V6: hold within limit ───
        if a.arr - earliest > station.max_hold:
            C.append(Conflict(code="HOLD_EXCEEDED", trains=[a.train_id], minutes=a.arr - earliest))

        # ─── V7: frozen trains keep platform and arrival ───
        f = frozen.get(a.train_id)
        if f is not None:
            # f is an Assignment (from the applied plan)
            f_plat = getattr(f, "platform", None)
            f_arr = getattr(f, "arr", None)
            if (f_plat, f_arr) != (a.platform, a.arr):
                C.append(Conflict(code="FROZEN_CHANGED", trains=[a.train_id]))

        # Record occupancy for sweep
        occ[a.platform].append((a.arr, a.dep, a.train_id))  # type: ignore[arg-type]

    # ─── V8: sweep line — no overlap, gap respected ───
    for pid, items in occ.items():
        items.sort()
        for i, (a1, d1, id1) in enumerate(items):
            for a2, d2, id2 in items[i + 1:]:
                if a2 >= d1 + gap:
                    break  # sorted, so all further are clear
                stay = max(0, min(d1, d2) - a2)                  # both physically at platform
                reserved = min(d1, d2) + gap - a2                # overlap of [arr, dep+gap) intervals
                C.append(Conflict(
                    code="OVERLAP" if stay > 0 else "GAP_VIOLATION",
                    trains=[id1, id2],
                    platform=pid,
                    stay_overlap_min=stay,
                    clearance_shortfall_min=None if stay > 0 else d1 + gap - a2,
                    reserved_overlap_min=reserved,
                ))

    # ─── V9: closure violations ───
    for c in disruptions.closures:
        for a, d, tid in occ.get(c.platform_id, []):
            if a < c.end and c.start < d + gap:
                C.append(Conflict(
                    code="CLOSURE_VIOLATION",
                    trains=[tid],
                    platform=c.platform_id,
                    reserved_overlap_min=min(d + gap, c.end) - max(a, c.start),
                    start=c.start,
                    end=c.end,
                ))

    return ValidationReport(
        valid=not C,
        conflicts=C,
        validator_version=VALIDATOR_VERSION,
        checked_rules=["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10"],
    )
