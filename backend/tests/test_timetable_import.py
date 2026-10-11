"""SPEC §20.10, §40 — the shipped workbook imports and reproduces its Answer key."""
import datetime as dt
import io

import pytest
from openpyxl import Workbook

from railflow.models import Disruptions, PlanInput, TimetableIn
from railflow.timetable_import import parse_upload
from railflow.validator import validate

from conftest import DATA, load_json

WB = (DATA / "demo" / "shivneri_timetable_demo.xlsx").read_bytes()
HEAD = ["Train No.", "Train Name", "Type", "From", "To", "Dir", "Arr", "Dep", "Halt (min)", "Sch. PF", "Req. PF",
        "Allowed PFs", "Coaches", "Wagons", "Days of run", "Priority"]


def _check(station, tti):
    tt = tti.to_timetable()
    return validate(station, tt, Disruptions(), PlanInput(station=station, timetable=tt).applied_revision(), None, 0)


def test_two_qualifying_sheets_need_a_choice(station):
    res = parse_upload("shivneri_timetable_demo.xlsx", WB, station)
    assert res["needs_sheet"] == ["Timetable as scheduled", "Timetable conflict-free"]


def test_as_scheduled_gives_the_answer_key(station):
    res = parse_upload("shivneri_timetable_demo.xlsx", WB, station, "Timetable as scheduled")
    assert len(res["timetable"].trains) == 30 and res["settings"] == {"min_gap": 5, "max_hold": 45}
    got = sorted((c.code, c.platform, tuple(c.trains), c.stay_overlap_min, c.reserved_overlap_min)
                 for c in _check(station, res["timetable"]).conflicts)
    assert got == [("GAP_VIOLATION", "P1", ("11214", "11216"), 0, 2), ("GAP_VIOLATION", "P2", ("51218", "51219"), 0, 3),
                   ("OVERLAP", "P4", ("51214", "51215"), 5, 10)]


def test_conflict_free_sheet(station):
    res = parse_upload("shivneri_timetable_demo.xlsx", WB, station, "Timetable conflict-free")
    assert _check(station, res["timetable"]).valid


@pytest.mark.parametrize("sheet,twin", [("Timetable as scheduled", "timetable_conflicts.json"),
                                        ("Timetable conflict-free", "timetable_normal.json")])
def test_json_twins_equal_workbook(station, sheet, twin):
    res = parse_upload("shivneri_timetable_demo.xlsx", WB, station, sheet)
    assert res["timetable"].model_dump() == TimetableIn.model_validate(load_json(twin)).model_dump()


def _book(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "TT"
    ws.append(HEAD)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ROW = ["11209", "Shivneri Fort Express (fictional)", "MEX", "BMGD", "DGWD", "DN", dt.time(14, 2), dt.time(14, 12),
       None, 3, None, "", 24, None, "Daily", 2]


def test_time_cells_and_text_both_import(station):
    text_row = list(ROW)
    text_row[0], text_row[6], text_row[7] = "11217", "14:50", "15:02"
    res = parse_upload("t.xlsx", _book([ROW, text_row]), station)
    tt = res["timetable"]
    assert [(t.arr, t.dep) for t in tt.trains] == [("14:02", "14:12"), ("14:50", "15:02")]
    assert tt.trains[0].allowed_platforms == ["P1", "P2", "P3", "P4"]        # derived: 24 coaches, not the bay


def test_departure_before_arrival_names_the_row(station):
    bad = list(ROW)
    bad[7] = dt.time(13, 0)
    res = parse_upload("t.xlsx", _book([ROW[:], bad]), station)
    assert res["errors"] and res["errors"][0].startswith("Row 3")
    assert "departure must be after arrival" in res["errors"][0]


def test_macro_workbook_refused(station):
    assert "errors" in parse_upload("t.xlsm", WB, station)


def test_csv_import(station):
    lines = [",".join(HEAD), "11209,Shivneri Fort Express (fictional),MEX,BMGD,DGWD,DN,14:02,14:12,10,3,,\"1,2,3,4\",24,,Daily,2"]
    res = parse_upload("t.csv", "\n".join(lines).encode(), station)
    assert res["timetable"].trains[0].platform == "P3"


def test_goods_derived_allowed_in_wagons(station):
    g = ["GDS-4105", "Plateau Goods (fictional)", "GDS", "KLGT", "NRGD", "DN", dt.time(12, 40), dt.time(12, 55),
         None, 4, None, "", None, 58, "Daily", 4]
    assert parse_upload("t.xlsx", _book([g]), station)["timetable"].trains[0].allowed_platforms == ["P4"]
