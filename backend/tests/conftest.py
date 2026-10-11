import json
import os
import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

PASSWORDS = {"viewer": "viewer-demo-pass-1", "controller": "controller-demo-pass-1", "admin": "admin-demo-pass-1"}
os.environ.setdefault("RAILFLOW_VIEWER_PASSWORD", PASSWORDS["viewer"])
os.environ.setdefault("RAILFLOW_CONTROLLER_PASSWORD", PASSWORDS["controller"])
os.environ.setdefault("RAILFLOW_ADMIN_PASSWORD", PASSWORDS["admin"])
os.environ["RAILFLOW_OLLAMA_URL"] = "http://127.0.0.1:9"      # tests never depend on a running Ollama


def load_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def station():
    from railflow.models import Station
    return Station.model_validate(load_json("station_shivneri.json"))


def timetable(name: str):
    from railflow.models import TimetableIn
    return TimetableIn.model_validate(load_json(name)).to_timetable()


@pytest.fixture(scope="session")
def tt_normal():
    return timetable("timetable_normal.json")


@pytest.fixture(scope="session")
def tt_conflicts():
    return timetable("timetable_conflicts.json")


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Fresh database file, fresh scenario store, seeded demo accounts."""
    from railflow import db, llm, manage, scenario_store
    from railflow.scenario_store import ScenarioStore

    db.set_path(tmp_path / "railflow.db")
    llm.reset_cache()
    monkeypatch.setattr(llm, "OLLAMA", "http://127.0.0.1:9")
    fresh = ScenarioStore()
    monkeypatch.setattr(scenario_store, "store", fresh)
    import railflow.main as main
    import railflow.admin as admin
    monkeypatch.setattr(main, "store", fresh)
    monkeypatch.setattr(admin, "store", fresh)
    db.startup()
    manage.seed_demo()
    yield main
    db.close_all()


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient
    with TestClient(app_env.app) as c:
        yield c


@pytest.fixture()
def make_client(app_env):
    from fastapi.testclient import TestClient
    made = []

    def _make():
        c = TestClient(app_env.app)
        c.__enter__()
        made.append(c)
        return c
    yield _make
    for c in made:
        c.__exit__(None, None, None)


def do_login(c, role: str):
    r = c.post("/api/auth/login", json={"username": role, "password": PASSWORDS[role]})
    assert r.status_code == 200, r.text
    return r


@pytest.fixture()
def login(client):
    return lambda role: do_login(client, role)


S2_TEXT = "11209 running 30 min late, platform 3 shut 14:00 to 15:30 for track inspection"
S2_CONFIRMED = [{"type": "delay", "train_id": "11209", "minutes": 30, "kind": "arrival"},
                {"type": "closure", "platform_id": "P3", "start": "14:00", "end": "15:30"}]
S8_CONFIRMED = [{"type": "delay", "train_id": "51218", "minutes": 25, "kind": "departure"},
                {"type": "closure", "platform_id": "P3", "start": "14:30", "end": "15:10"}]
PLAN = {"confirmed": S2_CONFIRMED, "now": "13:50"}
