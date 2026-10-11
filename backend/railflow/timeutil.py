"""HH:MM <-> integer minutes since 00:00. No midnight wrap (SPEC §6)."""
from __future__ import annotations

import re

DAY_END = 24 * 60  # exclusive


def to_min(s: str) -> int:
    """Strict 'HH:MM' (24 h) -> minutes since 00:00."""
    h, m = s.strip().split(":")
    hi, mi = int(h), int(m)
    if not (0 <= hi <= 23 and 0 <= mi <= 59):
        raise ValueError(f"not a 24-hour time: {s!r}")
    return hi * 60 + mi


def to_hhmm(x: int | None) -> str:
    if x is None:
        return "—"
    return f"{x // 60:02d}:{x % 60:02d}"


_LOOSE = re.compile(r"^\s*(\d{1,2})\s*[:.\s]?\s*(\d{2})\s*$")


def parse_loose_time(s: str) -> int | None:
    """Accepts '14:00', '14.00', '1400', '14 00', '9:05' -> minutes, else None.
    Spoken 24-hour times written as digits are normalised here (SPEC §41)."""
    if s is None:
        return None
    m = _LOOSE.match(str(s))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h * 60 + mi
    return None
