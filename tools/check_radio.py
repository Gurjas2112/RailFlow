"""Check the demo radio clips with the real speech model (SPEC §41). Run once on the demo laptop.

    pip install faster-whisper
    set RAILFLOW_STT=1   (PowerShell: $env:RAILFLOW_STT = "1")
    python tools/check_radio.py

Transcribes both clips, normalises, runs the regex parser and the proposal validator, prints the proposals.
Pass: the English clip yields delay 11209 +30 and closure P3 14:00–15:30. Never edit a clip to fit the model.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("RAILFLOW_STT", "1")

from railflow import stt  # noqa: E402
from railflow.models import Station, TimetableIn  # noqa: E402
from railflow.parser_regex import parse_regex  # noqa: E402
from railflow.proposals import normalise, validate_proposals  # noqa: E402
from railflow.timeutil import to_min  # noqa: E402


def main() -> int:
    if not stt.enabled():
        print("faster-whisper is not installed (pip install faster-whisper); nothing to check.")
        return 2
    st = Station.model_validate_json((ROOT / "data" / "station_shivneri.json").read_text(encoding="utf-8"))
    tt = TimetableIn.model_validate_json((ROOT / "data" / "timetable_normal.json").read_text(encoding="utf-8")).to_timetable()
    ids = [t.id for t in tt.trains]
    ok_en = False
    for clip, lang in (("radio_s2_en.wav", "en"), ("radio_s2_hi.wav", "hi")):
        res = stt.transcribe((ROOT / "data" / "demo" / clip).read_bytes(), lang, ids, [p.name for p in st.platforms])
        print(f"\n{clip} [{res['stt_path']}]\n  transcript: {res['transcript']!r}")
        norm = normalise(res["transcript"], ids)
        parsed = parse_regex(norm.text)
        ok, rej, _ = validate_proposals(parsed["events"], parsed["unparsed"], res["transcript"], st, tt, to_min("13:50"))
        for p in ok:
            print(f"  proposal: {p.type} {p.train_id or p.platform_id} {p.minutes or ''}{p.start or ''}{'–' + p.end if p.end else ''} [{p.status}]")
        for p in rej:
            print(f"  rejected: {p.message}")
        if lang == "en":
            got = {(p.type, p.train_id, p.minutes) for p in ok if p.type == "delay"} | \
                  {(p.type, p.platform_id, p.start, p.end) for p in ok if p.type == "closure"}
            ok_en = {("delay", "11209", 30), ("closure", "P3", "14:00", "15:30")} <= got
    print("\nPASS" if ok_en else "\nCHECK: English clip did not give both events; type the message on stage instead.")
    return 0 if ok_en else 1


if __name__ == "__main__":
    raise SystemExit(main())
