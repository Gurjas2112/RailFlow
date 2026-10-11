"""SPEC §20.7 — identity and access, all seven cases plus the role table of §17/§30."""
from conftest import PASSWORDS, PLAN, do_login

STRONG = "a-strong-new-password-42"


def _valid_revision(client):
    do_login(client, "controller")
    client.post("/api/scenario/load", json={"scenario_id": "S2"})
    rid = client.post("/api/plan", json=PLAN).json()["revisions"][0]["revision"]["id"]
    client.post("/api/auth/logout")
    return rid


def _last_audit(app_env):
    from railflow import audit, db
    return audit.last(db.get_conn())


def test_viewer_cannot_apply(client, app_env):
    rid = _valid_revision(client)
    do_login(client, "viewer")
    r = client.post(f"/api/revisions/{rid}/apply")
    assert r.status_code == 403
    assert _last_audit(app_env)["action"] == "refused"


def test_admin_cannot_plan_parse_or_apply(client, app_env):
    rid = _valid_revision(client)
    do_login(client, "admin")
    assert client.post("/api/plan", json=PLAN).status_code == 403
    assert client.post("/api/disruptions/parse", json={"text": "x"}).status_code == 403
    assert client.post(f"/api/revisions/{rid}/apply").status_code == 403
    assert _last_audit(app_env)["action"] == "refused"
    m = client.get("/api/admin/metrics").json()
    assert m["security"]["refused_by_role"].get("admin", 0) >= 3


def test_lockout_after_five_failures(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "controller", "password": "wrong-password"})
    r = client.post("/api/auth/login", json={"username": "controller", "password": PASSWORDS["controller"]})
    assert r.status_code == 429


def test_unknown_user_and_wrong_password_look_identical(client):
    a = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    b = client.post("/api/auth/login", json={"username": "controller", "password": "x"})
    assert (a.status_code, a.json()) == (b.status_code, b.json()) == (401, {"detail": "Invalid username or password"})


def test_invite_is_single_use(client):
    do_login(client, "admin")
    inv = client.post("/api/admin/users/invite", json={"username": "newctrl", "role": "controller"}).json()
    client.post("/api/auth/logout")
    body = {"token": inv["token"], "password": STRONG}
    assert client.post("/api/auth/accept-invite", json=body).status_code == 200
    assert client.post("/api/auth/accept-invite", json=body).status_code == 410
    assert client.post("/api/auth/login", json={"username": "newctrl", "password": STRONG}).json()["role"] == "controller"


def test_weak_password_refused_on_invite(client):
    do_login(client, "admin")
    inv = client.post("/api/admin/users/invite", json={"username": "weakling", "role": "viewer"}).json()
    assert client.post("/api/auth/accept-invite", json={"token": inv["token"], "password": "short"}).status_code == 422


def test_cross_origin_post_refused(client):
    do_login(client, "controller")
    r = client.post("/api/plan", json=PLAN, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_disabled_user_session_dies_immediately(make_client):
    ctrl, adm = make_client(), make_client()
    do_login(ctrl, "controller")
    do_login(adm, "admin")
    assert ctrl.get("/api/auth/me").status_code == 200
    assert adm.patch("/api/admin/users/controller", json={"disabled": True}).status_code == 200
    assert ctrl.get("/api/auth/me").status_code == 401


def test_last_admin_cannot_be_demoted(client):
    do_login(client, "admin")
    assert client.patch("/api/admin/users/admin", json={"role": "viewer"}).status_code == 409
    assert client.patch("/api/admin/users/admin", json={"disabled": True}).status_code == 409


def test_session_cookie_flags(client):
    r = do_login(client, "viewer")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie


def test_viewer_reads_but_cannot_act(client):
    do_login(client, "viewer")
    assert client.get("/api/scenario").status_code == 200
    assert client.get("/api/audit").status_code == 200
    assert client.post("/api/scenario/reset").status_code == 403
    assert client.get("/api/audit/verify").status_code == 403
    assert client.get("/api/admin/metrics").status_code == 403


def test_unauthenticated_is_401(client):
    assert client.get("/api/scenario").status_code == 401
    assert client.post("/api/plan", json=PLAN).status_code == 401


def test_language_is_remembered_per_user(client):
    do_login(client, "viewer")
    assert client.patch("/api/auth/me", json={"lang": "mr"}).json()["lang"] == "mr"
    client.post("/api/auth/logout")
    assert do_login(client, "viewer").json()["lang"] == "mr"
