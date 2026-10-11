"""Generate RailFlow's derived data, deterministically (seed 42). SPEC §6, §20.4, §22, §40, §47.7.

Writes:
  data/timetable_peak.json   36 trains: the 30 shipped trains + 6 seeded extras, conflict-free as scheduled
  data/scenarios.json        S1–S8 and the negative test S2-late
  data/parser_eval.jsonl     50 labelled operator messages (10 in Devanagari) + the 2 radio transcripts

Never touches the shipped files (station, normal/conflict timetables, workbook, clips). Asserts the
JSON twins equal the workbook import, so S1/S3 and the uploaded workbook always agree.

    python tools/make_data.py
"""
from __future__ import annotations

import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DATA = ROOT / "data"

from railflow.models import Disruptions, PlanInput, Station, TimetableIn  # noqa: E402
from railflow.timetable_import import parse_upload  # noqa: E402
from railflow.timeutil import to_hhmm  # noqa: E402
from railflow.validator import validate  # noqa: E402

SEED = 42


def check_twins(station: Station) -> None:
    data = (DATA / "demo" / "shivneri_timetable_demo.xlsx").read_bytes()
    for sheet, twin in (("Timetable as scheduled", "timetable_conflicts.json"),
                        ("Timetable conflict-free", "timetable_normal.json")):
        res = parse_upload("shivneri_timetable_demo.xlsx", data, station, sheet)
        assert "timetable" in res, res.get("errors")
        want = TimetableIn.model_validate_json((DATA / twin).read_text(encoding="utf-8"))
        assert res["timetable"].model_dump() == want.model_dump(), f"{twin} differs from workbook sheet {sheet!r}"
        assert res["settings"] == {"min_gap": station.min_gap, "max_hold": station.max_hold}, res["settings"]
    print("JSON twins equal the workbook import: ok")


EXTRAS = [  # id, name, type, origin, destination, direction, coaches (wagons for GDS), dwell
    ("12241", "Malshej Ghat SF Express (fictional)", "SF", "AMBP", "CNDP", "DN", 26, 10),
    ("11243", "Lenyadri Express (fictional)", "MEX", "BMGD", "DGWD", "DN", 24, 12),
    ("51245", "Kukadi Passenger (fictional)", "PAS", "EKLN", "HRGD", "DN", 18, 15),
    ("51247", "Ghod Valley Passenger (fictional)", "PAS", "HRGD", "EKLN", "UP", 18, 10),
    ("11249", "Junnar Fort Express (fictional)", "MEX", "DGWD", "BMGD", "UP", 24, 10),
    ("GDS-4241", "Plateau Goods (BOXN rake) (fictional)", "GDS", "NRGD", "KLGT", "UP", 58, 15),
]
ALLOWED = {"SF": ["P1", "P2"], "MEX": ["P1", "P2", "P3", "P4"], "PAS": ["P1", "P2", "P3", "P4"], "GDS": ["P4"]}
PRIORITY = {"SF": 1, "MEX": 2, "PAS": 3, "GDS": 4}
WINDOW = {"GDS": (15 * 60, 15 * 60 + 40)}           # the goods path lands inside the S6 closure window


def make_peak(station: Station) -> dict:
    base = json.loads((DATA / "timetable_normal.json").read_text(encoding="utf-8"))
    tt = TimetableIn.model_validate(base).to_timetable()
    gap = station.min_gap
    busy: dict[str, list[tuple[int, int]]] = {}
    for t in tt.trains:
        busy.setdefault(t.platform, []).append((t.arr, t.dep + gap))
    rng = random.Random(SEED)
    rows = list(base["trains"])
    for tid, name, typ, o, d, direction, coaches, dwell in sorted(EXTRAS, key=lambda e: e[2] != "GDS"):
        for _ in range(500):
            lo, hi = WINDOW.get(typ, (15 * 60, 16 * 60 + 10))
            arr = rng.randint(lo, hi)
            pf = rng.choice(ALLOWED[typ])
            end = arr + dwell + gap
            if all(end <= a or b <= arr for a, b in busy.get(pf, [])):
                busy.setdefault(pf, []).append((arr, end))
                rows.append({"id": tid, "name": name, "type": typ, "origin": o, "destination": d,
                             "direction": direction, "arr": to_hhmm(arr), "dep": to_hhmm(arr + dwell), "platform": pf,
                             "required_platform": None, "allowed_platforms": ALLOWED[typ],
                             "coaches": None if typ == "GDS" else coaches, "wagons": coaches if typ == "GDS" else None, "days": "Daily", "priority": PRIORITY[typ]})
                break
        else:
            raise SystemExit(f"could not place {tid}")
    rows.sort(key=lambda r: (r["arr"], r["id"]))
    peak = {"station": "SVNJ", "day": "Sun", "trains": rows}
    ptt = TimetableIn.model_validate(peak).to_timetable()
    rep = validate(station, ptt, Disruptions(), PlanInput(station=station, timetable=ptt).applied_revision(), None, 0)
    assert rep.valid and len(ptt.trains) == 36, rep.conflicts
    return peak


S2_TEXT = "11209 running 30 min late, platform 3 shut 14:00 to 15:30 for track inspection"
S8_TEXT = "51218 held at platform 2, departure 25 min late. Platform 3 closed 14:30 to 15:10 for a points check"

SCENARIOS = [
    {"id": "S1", "name": "Normal day — assign platforms", "timetable_file": "timetable_normal.json", "now": 720,
     "expect": "VALID · FULLY ASSIGNED · 0 changes", "proves": "Conflict-free assignment, required platforms honoured"},
    {"id": "S2", "name": "Radio report — delay + closure", "timetable_file": "timetable_normal.json", "now": 830,
     "text": S2_TEXT, "expect": "Affected 3 of 30 · 3 moves · hold 16 · weighted 45 · all revisions agree",
     "proves": "Transcribe → parse → confirm → revisions → explain → apply"},
    {"id": "S2-late", "name": "Same report at 14:05 (negative)", "timetable_file": "timetable_normal.json", "now": 845,
     "text": S2_TEXT, "expect": "Delay rejected: 11209 is already at PF 3",
     "proves": "An arrival delay for a train already at its platform is rejected"},
    {"id": "S3", "name": "Spreadsheet conflicts", "timetable_file": "timetable_conflicts.json", "now": 720,
     "expect": "GAP P1 11214↔11216 2 · GAP P2 51218↔51219 3 · OVERLAP P4 51214↔51215 5/10",
     "proves": "Detection by train and platform with minutes, matching the workbook's Answer key"},
    {"id": "S4", "name": "Unknown train", "timetable_file": "timetable_normal.json", "now": 720,
     "text": "11299 delayed 20 min", "expect": "Rejected: 11299 is not in today's timetable",
     "proves": "Unknown train rejected, not guessed"},
    {"id": "S5", "name": "S8 + planner fault", "timetable_file": "timetable_normal.json", "now": 850,
     "text": S8_TEXT, "inject_fault": True, "expect": "A: OVERLAP P1 12222↔51215 · stays 7 · reserved 12 → NOT VALID",
     "proves": "Independent validator rejects; Apply disabled"},
    {"id": "S6", "name": "Peak + two platforms closed", "timetable_file": "timetable_peak.json", "now": 840,
     "text": "Platform 2 closed 15:00 to 16:30. Platform 4 closed 15:00 to 16:30",
     "expect": "Some trains UNASSIGNED with reasons · plan still VALID (PARTIAL)",
     "proves": "UNASSIGNED with reasons; plan still valid"},
    {"id": "S7", "name": "Ollama stopped", "timetable_file": "timetable_normal.json", "now": 830, "text": S2_TEXT,
     "expect": "parser: regex · explainer: template · same plan as S2",
     "proves": "Regex parser + template explainer; path chips flip"},
    {"id": "S8", "name": "Delay cascade", "timetable_file": "timetable_normal.json", "now": 850, "text": S8_TEXT,
     "expect": "Affected 4 of 30 · A 2 moves / weighted 76 · B 1 move / weighted 136",
     "proves": "Affected 4 of 30; real trade-off A vs B; chain 51218 → 51215"},
]


def D(train: str, minutes: int, kind: str = "arrival") -> dict:
    return {"type": "delay", "train_id": train, "minutes": minutes, "kind": kind}


def C(pf: str, start: str, end: str) -> dict:
    return {"type": "closure", "platform_id": pf, "start": start, "end": end}


def parser_eval() -> list[dict]:
    """50 labelled operator messages: clean, paraphrase, Hinglish, multi-event, unknown IDs,
    non-existent platforms, noise and 10 in Devanagari; train numbers and minutes drawn with seed 42."""
    rng = random.Random(SEED)
    trains = ["11209", "11217", "11225", "11236", "12222", "12230", "12233", "51215", "51219", "51222", "51226", "51234"]
    at_pf = ["51218", "11216"]                                  # at a platform around 14:05 (departure wording)
    pick = lambda: rng.choice(trains)                           # noqa: E731
    mins = lambda: rng.choice([5, 8, 10, 12, 15, 20, 25, 30, 35, 40])  # noqa: E731
    rows: list[dict] = []

    def add(category: str, lang: str, text: str, expected: list[dict], reject: list[str] | None = None, now: str = "13:00"):
        rows.append({"id": f"P{len(rows) + 1:02d}", "category": category, "lang": lang, "now": now, "text": text,
                     "expected": expected, "expect_rejected": reject or []})

    for _ in range(8):                                          # clean
        t, m = pick(), mins()
        add("clean", "en", f"{t} running {m} min late", [D(t, m)])
    for pf, s, e in (("P3", "14:00", "15:30"), ("P1", "15:10", "15:40"), ("P4", "13:30", "14:15"), ("P5", "16:00", "16:30")):
        add("clean", "en", f"Platform {pf[1]} closed {s} to {e} for track work", [C(pf, s, e)])
    for text_fn in (lambda t, m: f"{t} is half an hour behind", lambda t, m: f"{t} will be about {m} minutes behind schedule",
                    lambda t, m: f"Expect {t} {m} mins late at SVNJ", lambda t, m: f"Delay of {m} minutes reported for {t}",
                    lambda t, m: f"{t} lost {m} min near the ghat section", lambda t, m: f"{t} is running behind by {m} minutes"):
        t, m = pick(), mins()
        text = text_fn(t, m)
        add("paraphrase", "en", text, [D(t, 30 if "half an hour" in text else m)])
    add("paraphrase", "en", "PF 2 will not be available from 15:00 till 15:45, OHE work", [C("P2", "15:00", "15:45")])
    add("paraphrase", "en", "Engineering block on platform 4 between 13:40 and 14:20", [C("P4", "13:40", "14:20")])
    for t in at_pf:
        m = mins()
        add("departure", "en", f"{t} held at platform, departure {m} min late", [D(t, m, "departure")], now="14:05")
    add("departure", "en", "51218 will leave 15 minutes late from PF 2", [D("51218", 15, "departure")], now="14:05")
    t, m = pick(), mins()
    add("hinglish", "hinglish", f"{t} {m} min late hai", [D(t, m)])
    add("hinglish", "hinglish", "PF 3 band hai 2 baje se 3:30 tak", [C("P3", "14:00", "15:30")])
    add("hinglish", "hinglish", "Platform 1 band 15:00 se 15:30 tak", [C("P1", "15:00", "15:30")])
    t, m = pick(), mins()
    add("hinglish", "hinglish", f"{t} {m} minute der se aa rahi hai", [D(t, m)])
    for _ in range(4):                                          # two events
        t, m = pick(), mins()
        add("multi", "en", f"{t} running {m} min late, platform 3 shut 14:00 to 15:30 for track inspection",
            [D(t, m), C("P3", "14:00", "15:30")])
    t1, t2 = rng.sample(trains, 2)
    add("multi", "en", f"{t1} delayed 10 min; {t2} delayed 20 min", [D(t1, 10), D(t2, 20)])
    for bad in ("11299", "12999", "51299"):                     # unknown trains: must be rejected, never guessed
        add("unknown_train", "en", f"{bad} delayed 20 min", [], reject=[bad])
    add("bad_platform", "en", "Platform 7 closed 14:00 to 15:00", [], reject=["P7"])
    add("bad_platform", "en", "PF 9 shut 15:00 to 16:00 for cleaning", [], reject=["P9"])
    add("noise", "en", "Inspection team to report at control at 16:00", [])
    add("noise", "en", "Tea stall on PF 1 is closed today", [])
    add("noise", "en", "Shift handover complete, all clear", [])
    dev = [  # 10 Devanagari: Hindi and Marathi (LLM path only, §37)
        ("hi", "गाड़ी संख्या 11209 तीस मिनट देरी से चल रही है", [D("11209", 30)]),
        ("hi", "प्लेटफॉर्म 3 दो बजे से साढ़े तीन बजे तक बंद", [C("P3", "14:00", "15:30")]),
        ("hi", "गाड़ी ११२१७ २० मिनट देरी से", [D("11217", 20)]),
        ("hi", "51215 पंद्रह मिनट लेट है", [D("51215", 15)]),
        ("hi", "प्लेटफॉर्म 4 15:00 से 16:00 तक बंद रहेगा", [C("P4", "15:00", "16:00")]),
        ("mr", "11209 तीस मिनिटे उशिरा, फलाट ३ दुपारी २ ते ३:३० बंद", [D("11209", 30), C("P3", "14:00", "15:30")]),
        ("mr", "गाडी ११२२५ दहा मिनिटे उशिरा आहे", [D("11225", 10)]),
        ("mr", "फलाट 2 15:00 ते 15:45 बंद राहील", [C("P2", "15:00", "15:45")]),
        ("mr", "51218 सुटण्यास 25 मिनिटे उशीर", [D("51218", 25, "departure")]),
        ("mr", "गाडी ११२९९ वीस मिनिटे उशिरा", []),
    ]
    for lang, text, exp in dev:
        add("devanagari", lang, text, exp, reject=["11299"] if "११२९९" in text else [],
            now="14:05" if "सुटण्यास" in text else "13:00")
    transcripts = (DATA / "demo" / "radio_transcripts.txt").read_text(encoding="utf-8").splitlines()
    en = next(line for line in transcripts if line.startswith("Shivneri control"))
    hi = next(line for line in transcripts if line.startswith("शिवनेरी"))
    add("radio", "en", en, [D("11209", 30), C("P3", "14:00", "15:30")], now="13:50")
    add("radio", "hi", hi, [D("11209", 30), C("P3", "14:00", "15:30")], now="13:50")
    assert len(rows) == 52 and sum(r["category"] == "devanagari" for r in rows) == 10, len(rows)
    return rows


def main() -> None:
    station = Station.model_validate_json((DATA / "station_shivneri.json").read_text(encoding="utf-8"))
    check_twins(station)
    peak = make_peak(station)
    (DATA / "timetable_peak.json").write_text(json.dumps(peak, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("data/timetable_peak.json: 36 trains, 0 conflicts as scheduled")
    (DATA / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"data/scenarios.json: {', '.join(s['id'] for s in SCENARIOS)}")
    rows = parser_eval()
    (DATA / "parser_eval.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                            encoding="utf-8")
    print(f"data/parser_eval.jsonl: {len(rows)} messages ({sum(r['category'] == 'devanagari' for r in rows)} Devanagari)")


if __name__ == "__main__":
    main()
