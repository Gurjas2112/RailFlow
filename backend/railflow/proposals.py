"""Deterministic proposal validator and input normalisation (SPEC §10.1, §37, §41, §43).

Runs on both LLM and regex output. Nothing here is AI:
- normalise(): Devanagari digits → 0–9, spaced/spoken train numbers → 11209, spoken 24-hour
  times (1400, 14.00, "14 00 to") → 14:00, Hindi/Marathi minute words → "min". Keeps an index
  map so every source span can be highlighted in the operator's ORIGINAL text.
- validate_proposals(): source span is a substring, IDs resolve (never guessed), aliases
  match, ranges hold, and the train's state at `now` allows the delay kind.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Iterable, Optional

from .models import Assignment, Proposal, ReasonPart, Station, Timetable
from .timeutil import parse_loose_time, to_hhmm, to_min

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
PROPOSAL_CODES = ["SOURCE_NOT_FOUND", "UNKNOWN_TRAIN", "UNKNOWN_PLATFORM", "MINUTES_OUT_OF_RANGE",
                  "BAD_TIME", "CLOSURE_ORDER", "ALREADY_DEPARTED", "AT_PLATFORM", "AMBIGUOUS", "INCONSISTENT"]


# ─────────────────────────── normalisation with an index map ───────────────────────────

class Normalised:
    """`text` with `index[i]` = position in the original string of output char i."""

    def __init__(self, original: str):
        self.original = original
        self.text = original.translate(_DEV_DIGITS)          # same length, 1:1
        self.index = list(range(len(original)))

    def sub(self, pattern: re.Pattern, repl) -> None:
        out, idx, pos = [], [], 0
        for m in pattern.finditer(self.text):
            new = repl(m)
            if new is None or new == m.group(0):
                continue
            out.append(self.text[pos:m.start()]); idx.extend(self.index[pos:m.start()])
            out.append(new)
            s, e = self.index[m.start()], self.index[m.end() - 1]
            idx.extend([s] * (len(new) - 1) + [e] if new else [])
            pos = m.end()
        out.append(self.text[pos:]); idx.extend(self.index[pos:])
        self.text, self.index = "".join(out), idx

    def span(self, sub: str) -> Optional[list[int]]:
        """[start, end) of `sub` in the original text, searching normalised text."""
        if not sub:
            return None
        i = self.original.find(sub)
        if i >= 0:
            return [i, i + len(sub)]
        i = self.text.find(sub)
        if i < 0:
            i = self.text.find(sub.translate(_DEV_DIGITS))
            if i < 0:
                return None
            sub = sub.translate(_DEV_DIGITS)
        return [self.index[i], self.index[i + len(sub) - 1] + 1]


_SPACED_ID = re.compile(r"(?<![\d:])(\d(?:[ \-]\d){4})(?![\d:])")          # 1 1 2 0 9
_SPLIT_ID = re.compile(r"(?<![\d:])(\d{1,4}) (\d{1,4})(?![\d:])")             # 11 209
_HHMM = re.compile(r"(?<![\d:.])([01]\d|2[0-3])(?:\.|)([0-5]\d)(?![\d:.])(?!\s*(?:min|mins|minutes|m)\b)", re.I)
_HH_MM_SPACE = re.compile(r"(?<![\d:])([01]\d|2[0-3]) ([0-5]\d)(?=\s*(?:to|till|until|-|–|hrs|hours|se|ते|से)\b|\s*$)", re.I)
_MIN_WORDS = re.compile(r"मिनटों|मिनट|मिनिटे|मिनिट")
_PF_WORDS = re.compile(r"platform\s+number\s+|platform\s+no\.?\s*", re.I)


def normalise(text: str, train_ids: Iterable[str] = ()) -> Normalised:
    ids = set(train_ids)
    n = Normalised(text)
    n.sub(_SPACED_ID, lambda m: (j if (j := re.sub(r"[ \-]", "", m.group(1))) in ids else None))
    n.sub(_SPLIT_ID, lambda m: (j if len(j := m.group(1) + m.group(2)) == 5 and j in ids else None))
    n.sub(_HHMM, lambda m: f"{m.group(1)}:{m.group(2)}" if len(m.group(0)) in (4, 5) else None)
    n.sub(_HH_MM_SPACE, lambda m: f"{m.group(1)}:{m.group(2)}")
    n.sub(_MIN_WORDS, lambda m: "min")
    n.sub(_PF_WORDS, lambda m: "platform ")
    return n


def normalise_train_id(raw: str, train_ids: set[str]) -> Optional[str]:
    """Strip spaces/hyphens, uppercase, Devanagari digits, insert the GDS hyphen; never guess."""
    s = re.sub(r"[\s\-]+", "", str(raw).translate(_DEV_DIGITS)).upper()
    s = re.sub(r"^(?:TRAIN|NO\.?|गाड़ी|गाडी|संख्या|क्रमांक)+", "", s)
    if (m := re.fullmatch(r"GDS(\d{4})", s)):
        s = f"GDS-{m.group(1)}"
    return s if s in train_ids else None


def resolve_platform(raw: str, station: Station) -> Optional[str]:
    """Alias table lookup (deterministic, §6); digits normalised first."""
    key = " ".join(str(raw).translate(_DEV_DIGITS).strip().lower().split())
    for p in station.platforms:
        if key in (p.id.lower(), p.name.lower()) or key in {" ".join(a.lower().split()) for a in p.aliases}:
            return p.id
    return None


def _hhmm_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    m = parse_loose_time(str(v).translate(_DEV_DIGITS))
    return to_hhmm(m) if m is not None else None


# ─────────────────────────── validation ───────────────────────────

def validate_proposals(
    events: list[dict[str, Any]],
    unparsed: list[str],
    text: str,
    station: Station,
    timetable: Timetable,
    now: int = 0,
    applied: Optional[dict[str, Assignment]] = None,
) -> tuple[list[Proposal], list[Proposal], list[str]]:
    """Return (proposals, rejected, unparsed). Proposals may be `ok` or `needs_clarification`."""
    train_ids = {t.id for t in timetable.trains}
    norm = normalise(text, train_ids)
    slots = applied or {}
    tt = timetable.by_id()
    ok: list[Proposal] = []
    rejected: list[Proposal] = []

    def reject(p: Proposal, code: str, message: str, **params) -> None:
        p.status, p.message, p.reason = "rejected", message, ReasonPart(code=code, params=params)
        rejected.append(p)

    for ev in events:
        source = str(ev.get("source") or "")
        span = norm.span(source)
        ambiguous = bool(ev.get("ambiguous"))
        if ev.get("type") == "delay":
            raw = str(ev.get("train_id") or "")
            tid = normalise_train_id(raw, train_ids)
            try:
                minutes = int(ev.get("minutes") or 0)
            except (TypeError, ValueError):
                minutes = 0
            kind = ev.get("kind") if ev.get("kind") in ("arrival", "departure") else "arrival"
            p = Proposal(id=uuid.uuid4().hex[:8], type="delay", train_id=tid, train_ref=raw, minutes=minutes,
                         kind=kind, source=source, span=span, ambiguous=ambiguous)
            if span is None:
                reject(p, "SOURCE_NOT_FOUND", "Not found in your message")
            elif tid is None:
                reject(p, "UNKNOWN_TRAIN", f"{raw or '?'} is not in today's timetable", train=raw)
            elif not 1 <= minutes <= 600:
                reject(p, "MINUTES_OUT_OF_RANGE", f"Delay of {minutes} min is out of range (1–600)", minutes=minutes)
            else:
                a = slots.get(tid)
                arr = a.arr if a and a.status == "ASSIGNED" and a.arr is not None else tt[tid].arr
                dep = a.dep if a and a.status == "ASSIGNED" and a.dep is not None else tt[tid].dep
                pf = a.platform if a and a.platform else tt[tid].platform
                if dep <= now:
                    reject(p, "ALREADY_DEPARTED", f"{tid} has already departed", train=tid)
                elif kind == "arrival" and arr <= now:
                    reject(p, "AT_PLATFORM", f"{tid} is already at {pf}; only a departure delay can apply",
                           train=tid, platform=pf or "")
                else:
                    _accept(p, ok)
        elif ev.get("type") == "closure":
            raw = str(ev.get("platform") or ev.get("platform_id") or "")
            pid = resolve_platform(raw, station)
            start, end = _hhmm_or_none(ev.get("start")), _hhmm_or_none(ev.get("end"))
            p = Proposal(id=uuid.uuid4().hex[:8], type="closure", platform_id=pid, platform_ref=raw,
                         start=start, end=end, source=source, span=span, ambiguous=ambiguous)
            if span is None:
                reject(p, "SOURCE_NOT_FOUND", "Not found in your message")
            elif pid is None:
                reject(p, "UNKNOWN_PLATFORM", f"Platform {raw or '?'} does not exist at {station.name}",
                       platform=raw, station=station.name)
            elif start is None or end is None:
                reject(p, "BAD_TIME", f"Cannot read the times {ev.get('start')}–{ev.get('end')}",
                       start=str(ev.get("start")), end=str(ev.get("end")))
            elif to_min(start) >= to_min(end):
                reject(p, "CLOSURE_ORDER", f"Closure start {start} must be before end {end}", start=start, end=end)
            else:
                _accept(p, ok)
    return ok, rejected, [u for u in unparsed if u and u.strip()]


_DEP_WORDS = re.compile(r"depart|leav|held at|late departure|प्रस्थान|रवाना|सुटण|सुटेल|निघ", re.I)
_PF_IN_SRC = re.compile(r"(?:platform|\bpf|\bp|प्लेटफॉर्म|प्लॅटफॉर्म|फलाट|पीएफ)\s*(?:no\.?|नंबर)?\s*-?\s*(\d{1,2})\b", re.I)


def inconsistency(p: Proposal) -> Optional[str]:
    """Deterministic cross-check of a proposal against its own source span. Catches a parser (LLM or regex)
    that copies the right words but reports different numbers. None if consistent or not checkable."""
    src = normalise(p.source or "").text
    nums = re.findall(r"(?<![\d:])\d{1,3}(?![\d:])", src)
    if p.type == "delay":
        if p.minutes is not None and str(p.minutes) not in nums:                 # e.g. "तीस मिनट", "half an hour"
            return f"{p.minutes} min is not written in “{p.source}”"
        if p.kind == "departure" and not _DEP_WORDS.search(src):
            return f"“{p.source}” does not describe a departure delay"
    else:
        pfs = {f"P{int(m)}" for m in _PF_IN_SRC.findall(src)}
        if pfs and p.platform_id not in pfs:
            return f"platform {p.platform_id} does not match “{p.source}”"
        times = {to_hhmm(t) for t in (parse_loose_time(x) for x in re.findall(r"\d{1,2}:\d{2}", src)) if t is not None}
        if not {p.start, p.end} <= times:                                        # e.g. "दो बजे", "2 baje"
            return f"{p.start}–{p.end} is not written in “{p.source}”"
    return None




def _accept(p: Proposal, ok: list[Proposal]) -> None:
    why = inconsistency(p)
    if why:
        p.status, p.message = "needs_clarification", f"Check before confirming: {why}"
        p.reason = ReasonPart(code="INCONSISTENT", params={"detail": why})
        ok.append(p)
        return
    if p.ambiguous:
        p.status, p.message = "needs_clarification", "Ambiguous — check and edit before confirming"
        p.reason = ReasonPart(code="AMBIGUOUS")
    else:
        p.status = "ok"
    ok.append(p)
