"""Regex fallback parser for disruption text (SPEC §10.1).

Used when Ollama is unreachable, times out, or returns schema-invalid JSON.
Handles English and romanised Hinglish. Devanagari-only messages are left
in `unparsed` for the operator to edit manually.
"""
from __future__ import annotations

import re
from typing import Any

TRAIN = r"(?P<train>\b(?:\d{5}|GDS[\s-]?\d{4})\b)"
MIN = r"(?P<min>\d{1,3})\s*(?:min|mins|minutes|m)\b"
TIME = r"(\d{1,2}[:\.]\d{2})"

DELAY_PATTERNS = [
    re.compile(
        TRAIN + r".{0,40}?(?:late|delay|delayed|behind|der|deri).{0,20}?" + MIN,
        re.I,
    ),
    re.compile(
        TRAIN + r".{0,40}?" + MIN + r".{0,15}?(?:late|delay|delayed|behind|der|deri)",
        re.I,
    ),
]

# Departure delay patterns
DEP_DELAY_PATTERNS = [
    re.compile(
        TRAIN + r"[^.;\n]{0,40}?(?:departure|depart|leaving|leave|held at platform|held at pf|late departure|will leave)"
        r"[^.;\n]{0,30}?" + MIN,
        re.I,
    ),
    re.compile(
        TRAIN + r".{0,40}?" + MIN + r".{0,15}?(?:departure|depart|leaving|late departure)",
        re.I,
    ),
]

_NO_PF = r"(?:(?!platform|\bpf|\bp\d)[^.;\n]){0,40}?"
_T = r"\d{1,2}[:\.]\d{2}|\d{1,2}\s*baje"
CLOSURE = re.compile(
    r"(?:platform|\bpf|\bp)\s*-?\s*(?P<plat>\d{1,2})\b" + _NO_PF +
    r"(?:closed|shut|blocked|unavailable|out of use|under block|band|बंद)"
    r"[^.;\n]{0,30}?(?P<t1>" + _T + r")\s*(?:-|–|to|till|until|tak|se)\s*(?P<t2>" + _T + r")",
    re.I,
)
# "closed from 14:00 to 15:30 on platform 3" — times before the platform
CLOSURE_REV = re.compile(
    r"(?:closed|shut|blocked|band)\s*(?:from\s*)?(?P<t1>" + _T + r")\s*(?:-|–|to|till|until|tak|se)\s*(?P<t2>" + _T +
    r")[^.;\n]{0,20}?(?:on\s+)?(?:platform|\bpf|\bp)\s*-?\s*(?P<plat>\d{1,2})\b",
    re.I,
)


def _normalise_time(t: str) -> tuple[str, bool]:
    """Normalise to HH:MM. "2 baje" is an hour with no AM/PM: afternoon assumed, flagged ambiguous."""
    t = t.strip()
    m = re.fullmatch(r"(\d{1,2})\s*baje", t, re.I)
    if m:
        h = int(m.group(1))
        return f"{(h + 12 if h < 8 else h):02d}:00", True
    h, mi = t.replace(".", ":").split(":")
    return f"{int(h):02d}:{int(mi):02d}", False


def _normalise_train_id(raw: str) -> str:
    """Normalise a raw train ID: strip spaces, insert hyphen for GDS."""
    tid = re.sub(r"\s+", "", raw).upper()
    # GDS with missing hyphen
    m = re.match(r"^GDS(\d{4})$", tid)
    if m:
        return f"GDS-{m.group(1)}"
    return tid


def parse_regex(text: str) -> dict[str, Any]:
    """Parse disruption text using regex patterns.

    Returns: {"events": [...], "unparsed": [...]}
    """
    events: list[dict[str, Any]] = []
    matched_spans: list[tuple[int, int]] = []

    # Try departure delay patterns first (more specific)
    for pat in DEP_DELAY_PATTERNS:
        for m in pat.finditer(text):
            tid = _normalise_train_id(m.group("train"))
            mins = int(m.group("min"))
            events.append({
                "type": "delay",
                "train_id": tid,
                "minutes": mins,
                "kind": "departure",
                "source": m.group(0).strip(),
            })
            matched_spans.append(m.span())

    # Regular delay patterns (skip if train was already captured as departure)
    dep_trains = {e["train_id"] for e in events}
    for pat in DELAY_PATTERNS:
        for m in pat.finditer(text):
            tid = _normalise_train_id(m.group("train"))
            if tid in dep_trains:
                continue
            mins = int(m.group("min"))
            events.append({
                "type": "delay",
                "train_id": tid,
                "minutes": mins,
                "kind": "arrival",
                "source": m.group(0).strip(),
            })
            matched_spans.append(m.span())

    # Closure patterns
    for pat in (CLOSURE, CLOSURE_REV):
        for m in pat.finditer(text):
            if any(not (m.end() <= a or b <= m.start()) for a, b in matched_spans):
                continue
            (start, amb1), (end, amb2) = _normalise_time(m.group("t1")), _normalise_time(m.group("t2"))
            ev = {"type": "closure", "platform": f"P{m.group('plat')}", "start": start, "end": end,
                  "source": m.group(0).strip()}
            if amb1 or amb2:
                ev["ambiguous"] = True
                sh, eh = int(start[:2]), int(end[:2])
                if eh * 60 + int(end[3:]) <= sh * 60 + int(start[3:]) and eh + 12 < 24:
                    ev["end"] = f"{eh + 12:02d}:{end[3:]}"      # "2 baje se 3:30 tak" → 14:00–15:30
            events.append(ev)
            matched_spans.append(m.span())

    # Find unparsed sentences
    unparsed: list[str] = []
    sentences = re.split(r"[.;!\n]+", text)
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 3:
            continue
        # Check if any match span overlaps with this sentence
        sent_start = text.find(sent)
        if sent_start < 0:
            continue
        sent_end = sent_start + len(sent)
        is_matched = any(
            not (sent_end <= ms or me <= sent_start)
            for ms, me in matched_spans
        )
        if not is_matched:
            unparsed.append(sent)

    return {"events": events, "unparsed": unparsed}
