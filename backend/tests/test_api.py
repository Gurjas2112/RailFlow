"""SPEC §20.6 and the Phase 2 gate, through the HTTP API."""
from conftest import PLAN, S2_CONFIRMED, S2_TEXT, S8_CONFIRMED


def _load(client, sid):
    r = client.post("/api/scenario/load", json={"scenario_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_is_public(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["db"] == "ok" and h["validator_version"] and h["ollama"] in ("up", "down")


def test_s2_end_to_end(client, login):
    login("controller")
    _load(client, "S2")
    parsed = client.post("/api/disruptions/parse", json={"text": S2_TEXT, "now": "13:50"}).json()
    assert parsed["parser_path"] == "regex" and not parsed["rejected"]
    assert {p["type"] for p in parsed["proposals"]} == {"delay", "closure"}
    confirmed = [{"type": "delay", "train_id": p["train_id"], "minutes": p["minutes"], "kind": p["kind"]}
                 if p["type"] == "delay" else
                 {"type": "closure", "platform_id": p["platform_id"], "start": p["start"], "end": p["end"]}
                 for p in parsed["proposals"]]
    r = client.post("/api/plan", json={"confirmed": confirmed, "now": "13:50", "source_text": S2_TEXT,
                                        "parser_path": "regex"})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert sorted(plan["affected"]) == ["11209", "11217", "51219"] and plan["agree"]
    for ro in plan["revisions"]:
        assert ro["validation"]["valid"] and ro["recovery"] == "FULLY_ASSIGNED"
        m = ro["metrics"]
        assert (m["platform_changes"], m["total_hold_min"], m["weighted_delay"], m["moved_outside_affected"]) == (3, 16, 45, 0)
    ids = [ro["revision"]["id"] for ro in plan["revisions"]]
    ex = client.post("/api/explain", json={"revision_ids": ids[:2], "lang": "en"}).json()
    assert ex["explainer_path"] == "template" and "45" in ex["text"]
    state = client.post(f"/api/revisions/{ids[0]}/apply").json()
    assert state["applied_revision_id"] == ids[0]
    a = {x["train_id"]: x for x in state["applied"]}
    assert (a["11209"]["platform"], a["11209"]["arr"]) == ("P4", 14 * 60 + 45)
    assert client.get("/api/audit").json()[0]["action"] == "apply"


def test_s2_late_rejected(client, login):
    login("controller")
    _load(client, "S2-late")
    parsed = client.post("/api/disruptions/parse", json={"text": S2_TEXT, "now": "14:05"}).json()
    assert [p["reason"]["code"] for p in parsed["rejected"]] == ["AT_PLATFORM"]
    r = client.post("/api/plan", json={"confirmed": S2_CONFIRMED, "now": "14:05"})
    assert r.status_code == 422                                  # a crafted body cannot bypass the gate


def test_s4_unknown_train(client, login):
    login("controller")
    _load(client, "S4")
    parsed = client.post("/api/disruptions/parse", json={"text": "11299 delayed 20 min"}).json()
    assert not parsed["proposals"] and parsed["rejected"][0]["reason"]["code"] == "UNKNOWN_TRAIN"


def test_s8_trade_off(client, login):
    login("controller")
    _load(client, "S8")
    plan = client.post("/api/plan", json={"confirmed": S8_CONFIRMED, "now": "14:10"}).json()
    got = {ro["revision"]["method"]: (ro["metrics"]["platform_changes"], ro["metrics"]["weighted_delay"])
           for ro in plan["revisions"]}
    assert got == {"cpsat_min_delay": (2, 76), "cpsat_min_changes": (1, 136), "greedy": (3, 85)}
    assert not plan["agree"] and len(plan["affected"]) == 4


def test_s5_fault_not_valid_and_apply_refused(client, login):
    login("controller")
    _load(client, "S5")
    plan = client.post("/api/plan", json={"confirmed": S8_CONFIRMED, "now": "14:10", "inject_fault": True}).json()
    a, b = plan["revisions"][0], plan["revisions"][1]
    assert plan["fault_injected"] and a["revision"]["fault_injected"] and not a["validation"]["valid"]
    c = a["validation"]["conflicts"]
    assert [(x["code"], x["platform"], x["trains"], x["stay_overlap_min"], x["reserved_overlap_min"]) for x in c] == \
        [("OVERLAP", "P1", ["12222", "51215"], 7, 12)]
    assert b["validation"]["valid"]                              # each revision judged on its own
    r = client.post(f"/api/revisions/{a['revision']['id']}/apply")
    assert r.status_code == 409 and "FAULT_INJECTED" in r.json()["detail"]


def test_s3_scheduled_then_assign(client, login):
    login("controller")
    _load(client, "S3")
    rep = client.post("/api/validate/scheduled").json()
    assert sorted((c["code"], c["platform"]) for c in rep["conflicts"]) == [
        ("GAP_VIOLATION", "P1"), ("GAP_VIOLATION", "P2"), ("OVERLAP", "P4")]
    plan = client.post("/api/assign", json={"now": "12:00"}).json()
    assert all(ro["validation"]["valid"] for ro in plan["revisions"])
    assert plan["revisions"][0]["metrics"]["platform_changes"] >= 1


def test_s6_partial_but_valid(client, login):
    login("controller")
    _load(client, "S6")
    closures = [{"type": "closure", "platform_id": p, "start": "15:00", "end": "16:30"} for p in ("P2", "P4")]
    plan = client.post("/api/plan", json={"confirmed": closures, "now": "14:00"}).json()
    a = plan["revisions"][0]
    assert a["validation"]["valid"] and a["recovery"] == "PARTIAL"
    un = [c for c in a["changes"] if c["cls"] == "UNASSIGNED"]
    assert un and all(any(p["code"] == "UNASSIGNED" for p in c["parts"]) for c in un)


def test_malformed_upload_422_with_field_errors(client, login):
    login("controller")
    r = client.post("/api/scenario/load", json={"timetable": {"trains": [{"id": "ABC", "arr": "25:00"}]}})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)
    r = client.post("/api/timetable/upload", files={"file": ("t.xlsm", b"x", "application/octet-stream")})
    assert r.status_code == 422 and r.json()["errors"]


def test_workbook_upload_needs_sheet_then_loads(client, login):
    from conftest import DATA
    login("controller")
    data = (DATA / "demo" / "shivneri_timetable_demo.xlsx").read_bytes()
    r = client.post("/api/timetable/upload", files={"file": ("demo.xlsx", data)}).json()
    assert r["needs_sheet"] == ["Timetable as scheduled", "Timetable conflict-free"]
    r = client.post("/api/timetable/upload", files={"file": ("demo.xlsx", data)},
                    data={"sheet": "Timetable as scheduled"}).json()
    state = client.post("/api/scenario/load", json={"station": r["station"], "timetable": r["timetable"],
                                                    "source": "upload"}).json()
    assert len(state["trains"]) == 30
    assert len(client.post("/api/validate/scheduled").json()["conflicts"]) == 3


def test_apply_invalid_revision_409(client, login, app_env):
    login("controller")
    _load(client, "S8")
    plan = client.post("/api/plan", json={"confirmed": S8_CONFIRMED, "now": "14:10", "inject_fault": True}).json()
    rid = plan["revisions"][0]["revision"]["id"]
    assert client.post(f"/api/revisions/{rid}/apply").status_code == 409


def test_parse_never_mutates_state(client, login):
    login("controller")
    _load(client, "S2")
    before = client.get("/api/scenario").json()
    client.post("/api/disruptions/parse", json={"text": S2_TEXT})
    assert client.get("/api/scenario").json() == before


def test_reset_restores_identical_results(client, login):
    login("controller")
    runs = []
    for _ in range(2):
        _load(client, "S8")
        client.post("/api/scenario/reset")
        plan = client.post("/api/plan", json={"confirmed": S8_CONFIRMED, "now": "14:10"}).json()
        runs.append([sorted((a["train_id"], a["platform"], a["arr"]) for a in ro["revision"]["assignments"]
                            if a["status"] == "ASSIGNED") for ro in plan["revisions"]])
    assert runs[0] == runs[1]


def test_stale_revision_after_another_apply(client, login):
    login("controller")
    _load(client, "S2")
    plan = client.post("/api/plan", json=PLAN).json()
    a, b = (ro["revision"]["id"] for ro in plan["revisions"][:2])
    assert client.post(f"/api/revisions/{a}/apply").status_code == 200
    r = client.post(f"/api/revisions/{b}/apply")
    assert r.status_code == 409 and "STALE_PLAN" in r.json()["detail"]


def test_second_disruption_after_apply_uses_the_applied_plan(client, login):
    login("controller")
    _load(client, "S2")
    plan = client.post("/api/plan", json=PLAN).json()
    client.post(f"/api/revisions/{plan['revisions'][0]['revision']['id']}/apply")
    more = [{"type": "delay", "train_id": "12222", "minutes": 10, "kind": "arrival"}]
    plan2 = client.post("/api/plan", json={"confirmed": more, "now": "14:00"}).json()
    assert all(ro["validation"]["valid"] for ro in plan2["revisions"])
    a = {x["train_id"]: x for x in plan2["revisions"][0]["revision"]["assignments"]}
    assert a["11209"]["platform"] == "P4" and a["12222"]["arr"] >= 14 * 60 + 40


def test_own_station_upload_assign_and_replan(client, login):
    """Not the demo station: the template workbook's 3-platform station, end to end through the API."""
    from conftest import DATA
    login("controller")
    data = (DATA.parent / "web" / "public" / "templates" / "railflow_template.xlsx").read_bytes()
    r = client.post("/api/timetable/upload", files={"file": ("mine.xlsx", data)}).json()
    assert r["station"]["id"] == "SHYR" and len(r["station"]["platforms"]) == 3
    state = client.post("/api/scenario/load", json={"station": r["station"], "timetable": r["timetable"],
                                                    "source": "upload:mine.xlsx"}).json()
    assert state["station"]["name"] == "Sahyadri Road (fictional)" and len(state["trains"]) == 8
    rep = client.post("/api/validate/scheduled").json()
    assert sorted(c["code"] for c in rep["conflicts"]) == ["GAP_VIOLATION", "OVERLAP"]
    plan = client.post("/api/assign", json={"now": "09:30"}).json()
    assert all(ro["validation"]["valid"] for ro in plan["revisions"])
    assert plan["revisions"][0]["recovery"] == "FULLY_ASSIGNED"
    client.post(f"/api/revisions/{plan['revisions'][0]['revision']['id']}/apply")
    parsed = client.post("/api/disruptions/parse", json={"text": "platform 2 closed 10:30 to 11:30, 12601 late 15 min",
                                                         "now": "09:40"}).json()
    ok = [p for p in parsed["proposals"] if p["status"] == "ok"]
    assert sorted(p["type"] for p in ok) == ["closure", "delay"]
    assert next(p for p in ok if p["type"] == "closure")["platform_id"] == "P2"
    confirmed = [{"type": "delay", "train_id": p["train_id"], "minutes": p["minutes"], "kind": p["kind"]}
                 if p["type"] == "delay" else
                 {"type": "closure", "platform_id": p["platform_id"], "start": p["start"], "end": p["end"]}
                 for p in ok]
    plan = client.post("/api/plan", json={"confirmed": confirmed, "now": "09:40"}).json()
    a = plan["revisions"][0]
    assert a["validation"]["valid"]
    on_p2 = [x for x in a["revision"]["assignments"] if x["platform"] == "P2" and x["arr"] is not None]
    assert all(x["dep"] + 5 <= 10 * 60 + 30 or x["arr"] >= 11 * 60 + 30 for x in on_p2)


def test_manual_timetable_before_now_starts_the_clock_before_its_first_train(client, login):
    """Typed in by hand (or uploaded) with trains earlier than "now": the clock moves back, so no train loads frozen."""
    login("controller")
    station = {"id": "MAN", "name": "Manual Jn (fictional)", "min_gap": 5,
               "platforms": [{"id": "P1", "name": "PF 1", "length_coaches": 24}, {"id": "P2", "name": "PF 2", "length_coaches": 24}]}
    row = {"name": "Typed (fictional)", "type": "PAS", "origin": "AAA", "destination": "BBB", "direction": "UP",
           "coaches": 12, "priority": 3, "platform": "P1", "allowed_platforms": ["P1", "P2"]}
    trains = [{**row, "id": "51001", "arr": "09:00", "dep": "09:10"}, {**row, "id": "51003", "arr": "09:12", "dep": "09:20"}]
    state = client.post("/api/scenario/load", json={"station": station, "timetable": {"trains": trains}, "source": "manual:MAN"}).json()
    assert state["now"] == 8 * 60 + 30
    assert {p["id"]: "platform 2" in p["aliases"] for p in state["station"]["platforms"]} == {"P1": False, "P2": True}
    plan = client.post("/api/assign", json={"now": "08:30"}).json()
    assert all(ro["validation"]["valid"] for ro in plan["revisions"])
