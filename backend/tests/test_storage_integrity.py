"""SPEC §20.8 — what is applied is exactly what was validated; history is tamper-evident."""
import sqlite3

import pytest

from conftest import PLAN, do_login


def _plan(client):
    do_login(client, "controller")
    client.post("/api/scenario/load", json={"scenario_id": "S2"})
    return client.post("/api/plan", json=PLAN).json()["revisions"][0]["revision"]["id"]


def test_altered_revision_refused_with_hash_mismatch(client, app_env):
    from railflow import db
    rid = _plan(client)
    raw = sqlite3.connect(str(db.DB_PATH), isolation_level=None)
    raw.execute("DROP TRIGGER revisions_no_update")
    raw.execute("UPDATE revisions SET assignments_json = replace(assignments_json, '\"P4\"', '\"P1\"') WHERE id = ?", (rid,))
    raw.close()
    r = client.post(f"/api/revisions/{rid}/apply")
    assert r.status_code == 409 and "HASH_MISMATCH" in r.json()["detail"]


def test_update_or_delete_on_audit_and_revisions_aborts(client, app_env):
    from railflow import db
    _plan(client)
    c = db.get_conn()
    for sql in ("UPDATE audit SET summary = 'x'", "DELETE FROM audit",
                "UPDATE revisions SET valid = 1", "DELETE FROM revisions"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)


def test_edited_audit_row_reported_by_verify(client, app_env):
    from railflow import db
    _plan(client)
    raw = sqlite3.connect(str(db.DB_PATH), isolation_level=None)
    raw.execute("DROP TRIGGER audit_no_update")
    seq = raw.execute("SELECT seq FROM audit ORDER BY seq LIMIT 1 OFFSET 2").fetchone()[0]
    raw.execute("UPDATE audit SET summary = 'nothing happened' WHERE seq = ?", (seq,))
    raw.close()
    client.post("/api/auth/logout")
    do_login(client, "admin")
    v = client.get("/api/audit/verify").json()
    assert v == {"intact": False, "entries": v["entries"], "first_broken_seq": seq}


def test_corrupted_database_refuses_writes(tmp_path):
    from fastapi.testclient import TestClient
    from railflow import db
    import railflow.main as main
    bad = tmp_path / "corrupt.db"
    bad.write_bytes(b"this is not a sqlite database" * 200)
    db.set_path(bad)
    try:
        with TestClient(main.app) as c:
            assert c.get("/api/health").json()["db"] == "integrity_failed"
            assert c.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 503
            assert c.post("/api/plan", json=PLAN).status_code == 503
    finally:
        db.close_all()


def test_revision_stores_its_validation_and_hash(client, app_env):
    import json
    from railflow import db
    rid = _plan(client)
    row = db.get_revision(db.get_conn(), rid)
    assert row["valid"] == 1 and json.loads(row["validation_json"])["valid"] is True
    assert db.sha256_text(row["assignments_json"]) == row["sha256"]
