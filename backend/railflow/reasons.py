"""Change reasons and diff classification (SPEC §11, §45).

Computed AFTER planning, deterministically, by comparing a revision with the applied plan.
The AI never writes a reason. Each reason is a list of `{code, params}` parts (rendered in
the browser in EN/हिं/मर from the locale files, §37) plus one English sentence for the
audit log. `caused_by` names the train or closure that blocked each held or moved train,
so the UI can follow the chain (51218 departs late → 51215 held).

Classes: FROZEN · UNCHANGED · DELAYED · HELD · MOVED · MOVED_HELD · UNASSIGNED
"""
from __future__ import annotations

from typing import Optional

from .models import ChangeItem, Closure, PlanInput, ReasonPart, Revision, Slot, Train
from .state import candidates, is_frozen_at, split_delays
from .timeutil import to_hhmm

CLASSES = ["FROZEN", "UNCHANGED", "DELAYED", "HELD", "MOVED", "MOVED_HELD", "UNASSIGNED"]

# Every reason code this module can emit; locale files must carry `reason.<CODE>` for each.
REASON_CODES = [
    "NO_CHANGE", "FROZEN", "FROZEN_DEPARTURE_DELAY",
    "ARRIVAL_DELAY", "DEPARTURE_DELAY",
    "MOVED_CLOSED", "MOVED_OCCUPIED", "MOVED_OTHER",
    "HELD_CLOSED", "HELD_OCCUPIED", "HELD_OTHER",
    "UNASSIGNED",
]

Occ = dict[str, list[tuple[int, int, str]]]


def _closure_id(c: Closure) -> str:
    return f"closure:{c.platform_id}:{to_hhmm(c.start)}-{to_hhmm(c.end)}"


def _blocker(platform: str, train_id: str, start: int, end: int, occ: Occ,
             closures: list[Closure], gap: int) -> Optional[tuple[str, dict]]:
    """What blocks the reserved interval [start, end) on `platform`: a closure first, then the
    train whose reservation overlaps it and ends latest."""
    for c in closures:
        if c.platform_id == platform and start < c.end and c.start < end:
            return "closed", {"start": to_hhmm(c.start), "end": to_hhmm(c.end), "id": _closure_id(c)}
    best = None
    for a, d, tid in occ.get(platform, []):
        if tid != train_id and start < d + gap and a < end:
            if best is None or d > best[1]:
                best = (tid, d)
    if best:
        return "occupied", {"train": best[0], "until": to_hhmm(best[1]), "gap": gap, "id": best[0]}
    return None


def _hold_blocker(platform: str, train_id: str, earliest: int, arr: int, occ: Occ,
                  closures: list[Closure], gap: int) -> Optional[tuple[str, dict]]:
    """The train or closure whose reservation ends latest within (earliest, arr] on `platform`."""
    best: Optional[tuple[int, str, dict]] = None
    for a, d, tid in occ.get(platform, []):
        end = d + gap
        if tid != train_id and earliest < end <= arr and (best is None or end > best[0]):
            best = (end, "occupied", {"train": tid, "until": to_hhmm(d), "gap": gap, "id": tid})
    for c in closures:
        if c.platform_id == platform and earliest < c.end <= arr and (best is None or c.end >= best[0]):
            best = (c.end, "closed", {"start": to_hhmm(c.start), "end": to_hhmm(c.end), "id": _closure_id(c)})
    return (best[1], best[2]) if best else None


def _unassigned_blockers(t: Train, inp: PlanInput, earliest: int, stay: int, occ: Occ) -> str:
    """Trains and closures occupying the candidate platforms during the hold window."""
    gap = inp.station.min_gap
    end = earliest + inp.station.max_hold + stay + gap
    names: list[str] = []
    for p in candidates(t, inp.station):
        for a, d, tid in sorted(occ.get(p, [])):
            if tid != t.id and a < end and earliest < d + gap and tid not in names:
                names.append(tid)
        for c in inp.disruptions.closures:
            if c.platform_id == p and c.start < end and earliest < c.end:
                names.append(f"{p} {to_hhmm(c.start)}–{to_hhmm(c.end)}")
    return ", ".join(names) or "—"


def _sentence(code: str, p: dict) -> str:
    """English rendering of one reason part (audit log; the UI uses the locale files)."""
    return {
        "NO_CHANGE": "No change",
        "FROZEN": "Departed or at platform at now; fixed",
        "FROZEN_DEPARTURE_DELAY": f"At platform; departure {p.get('minutes')} min late as reported",
        "ARRIVAL_DELAY": f"Running {p.get('minutes')} min late as reported",
        "DEPARTURE_DELAY": f"Departure delayed {p.get('minutes')} min as reported",
        "MOVED_CLOSED": f"moved {p.get('from')} → {p.get('to')}: {p.get('from')} closed {p.get('start')}–{p.get('end')}",
        "MOVED_OCCUPIED": (f"moved {p.get('from')} → {p.get('to')}: {p.get('from')} occupied by "
                           f"{p.get('train')} until {p.get('until')} + {p.get('gap')} min gap"),
        "MOVED_OTHER": f"moved {p.get('from')} → {p.get('to')}",
        "HELD_CLOSED": f"held {p.get('minutes')} min: {p.get('platform')} closed {p.get('start')}–{p.get('end')}",
        "HELD_OCCUPIED": (f"held {p.get('minutes')} min: {p.get('platform')} occupied by {p.get('train')} "
                          f"until {p.get('until')} + {p.get('gap')} min gap"),
        "HELD_OTHER": f"held {p.get('minutes')} min on {p.get('platform')}",
        "UNASSIGNED": (f"No platform free for {p.get('stay')} min within {p.get('max_hold')} min of "
                       f"{p.get('earliest')}; blocked by {p.get('blockers')}"),
    }[code]


def classify_and_reason(revision: Revision, inp: PlanInput) -> list[ChangeItem]:
    """Classify every train in `revision` and give each change its reasons."""
    applied = inp.applied_plan()
    orig = inp.timetable.by_id()
    arr_d, dep_d = split_delays(inp.disruptions)
    gap = inp.station.min_gap
    closures = inp.disruptions.closures
    affected = set(revision.affected)

    occ: Occ = {}
    for a in revision.assignments:
        if a.status == "ASSIGNED" and a.platform and a.arr is not None and a.dep is not None:
            occ.setdefault(a.platform, []).append((a.arr, a.dep, a.train_id))

    out: list[ChangeItem] = []
    for a in revision.assignments:
        t = orig.get(a.train_id)
        if t is None:
            continue
        ap = applied.get(a.train_id)
        before = Slot(platform=ap.platform, arr=ap.arr, dep=ap.dep) if ap and ap.status == "ASSIGNED" else None
        after = Slot(platform=a.platform, arr=a.arr, dep=a.dep)
        parts: list[ReasonPart] = []
        caused: list[str] = []
        earliest = t.arr + arr_d[t.id]
        stay = (t.dep - t.arr) + dep_d[t.id]

        def add(code: str, **params):
            parts.append(ReasonPart(code=code, params=params))

        if is_frozen_at(ap, inp.now) and a.status == "ASSIGNED":
            cls = "FROZEN"
            if before and a.dep != before.dep and dep_d[t.id]:
                add("FROZEN_DEPARTURE_DELAY", minutes=dep_d[t.id], platform=a.platform)
            else:
                add("FROZEN")
        elif a.status == "UNASSIGNED":
            cls = "UNASSIGNED"
            if arr_d[t.id]:
                add("ARRIVAL_DELAY", minutes=arr_d[t.id])
            add("UNASSIGNED", stay=stay, max_hold=inp.station.max_hold, earliest=to_hhmm(earliest),
                blockers=_unassigned_blockers(t, inp, earliest, stay, occ))
        elif before is None or (before.platform, before.arr, before.dep) == (a.platform, a.arr, a.dep):
            cls = "UNCHANGED"
            add("NO_CHANGE")
        else:
            moved = before.platform != a.platform
            cls = ("MOVED_HELD" if moved and a.hold else "MOVED" if moved
                   else "HELD" if a.hold else "DELAYED" if (arr_d[t.id] or dep_d[t.id]) else "UNCHANGED")
            if arr_d[t.id]:
                add("ARRIVAL_DELAY", minutes=arr_d[t.id])
            if dep_d[t.id]:
                add("DEPARTURE_DELAY", minutes=dep_d[t.id])
            if moved and before.platform:
                b = _blocker(before.platform, t.id, earliest, earliest + stay + gap, occ, closures, gap)
                if b and b[0] == "closed":
                    add("MOVED_CLOSED", **{"from": before.platform, "to": a.platform,
                                          "start": b[1]["start"], "end": b[1]["end"]})
                elif b:
                    add("MOVED_OCCUPIED", **{"from": before.platform, "to": a.platform, "train": b[1]["train"],
                                            "until": b[1]["until"], "gap": gap})
                else:
                    add("MOVED_OTHER", **{"from": before.platform, "to": a.platform})
                if b and b[1]["id"] not in caused:
                    caused.append(b[1]["id"])
            if a.hold and a.platform and a.arr is not None:
                h = _hold_blocker(a.platform, t.id, a.arr - a.hold, a.arr, occ, closures, gap)
                if h and h[0] == "closed":
                    add("HELD_CLOSED", minutes=a.hold, platform=a.platform, start=h[1]["start"], end=h[1]["end"])
                elif h:
                    add("HELD_OCCUPIED", minutes=a.hold, platform=a.platform, train=h[1]["train"],
                        until=h[1]["until"], gap=gap)
                else:
                    add("HELD_OTHER", minutes=a.hold, platform=a.platform)
                if h and h[1]["id"] not in caused:
                    caused.append(h[1]["id"])
            if cls == "UNCHANGED":
                add("NO_CHANGE")

        out.append(ChangeItem(
            train_id=t.id, cls=cls, before=before, after=after, hold=a.hold, parts=parts,
            text="; ".join(_sentence(p.code, p.params) for p in parts),
            caused_by=caused, affected=t.id in affected,
        ))
    return out
