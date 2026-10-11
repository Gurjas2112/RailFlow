"""RailFlow API — FastAPI, one process (SPEC §4, §17, §31, §39).

The AI branch (parse, explain) can only return proposals or text. Planning runs only on
disruptions a controller confirmed; every revision is validated by validator.py and stored
with the SHA-256 of its assignments; apply re-hashes, re-validates and commits in one transaction.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from . import audit, config, db, events, llm, stt
from .auth import COOKIE, accept_invite, actor, current_user, login as do_login, require_role
from .explainer import explain as explain_fn
from .fault import inject_fault
from .metrics import compute_metrics
from .models import (AcceptInviteRequest, AssignRequest, AuditVerify, Disruptions, ExplainRequest, ExplainResponse,
                     Health, LangRequest, LoginRequest, ParseRequest, ParseResponse, PlanRequest, PlanResponse,
                     Revision, RevisionOut, ScenarioInfo, ScenarioLoadRequest, ScenarioState, SessionOut, Station,
                     TimetableIn, TranscribeResponse, UploadResponse, ValidationReport, Assignment,
                     disruptions_from_in, recovery_status, referential_errors)
from .parser_llm import parse as parse_text
from .planner_cpsat import plan as plan_cpsat, plan_cpsat as plan_cpsat_full
from .planner_greedy import plan as plan_greedy, plan_greedy as plan_greedy_full
from .proposals import normalise, validate_proposals
from .reasons import classify_and_reason
from .scenario_store import LOCK, builtin_scenarios, store
from .security import SecurityMiddleware
from .timetable_import import parse_upload, to_json
from .timeutil import to_min
from .validator import VALIDATOR_VERSION, validate

LABELS = {"cpsat_min_delay": "A", "cpsat_min_changes": "B", "greedy": "G"}
METHODS = ("cpsat_min_delay", "cpsat_min_changes", "greedy")
_ollama_down_since: Optional[float] = None

viewer = require_role("viewer", "admin")              # read-only GETs (admin may read, never act)
controller = require_role("controller")
admin_only = require_role("admin")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    status = db.startup()
    if status == "ok" and not store.ready():
        store.load_builtin("S1", loaded_by="system")
    yield


app = FastAPI(title="RailFlow", version="1.7.0", lifespan=lifespan,
              description="Railway disruption & platform conflict simulator — advisory decision support on fictional data.")
if not config.serve_web():                            # same-origin in demo mode: no CORS at all (§33)
    app.add_middleware(CORSMiddleware, allow_origins=sorted(config.allowed_origins()), allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["content-type"])
app.add_middleware(SecurityMiddleware)


@app.exception_handler(ValidationError)
async def _pydantic_422(_req: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(e["loc"]), "msg": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]})


def _need_scenario() -> None:
    if not store.ready():
        raise HTTPException(409, "No scenario loaded")


# ───────────────────────────── health and scenarios ─────────────────────────────

@app.get("/api/health", response_model=Health)
def health() -> Health:
    global _ollama_down_since
    up = llm.ollama_up()
    _ollama_down_since = None if up else (_ollama_down_since or time.time())
    audit_state = "unknown"
    if db.STATUS == "ok":
        audit_state = "intact" if audit.verify(db.get_conn())["intact"] else "broken"
    return Health(ok=db.STATUS == "ok", ollama="up" if up else "down", model=llm.resolve_model() or "none",
                  validator_version=VALIDATOR_VERSION, db=db.STATUS, stt=stt.status(), audit=audit_state)


def ollama_down_seconds() -> float:
    return time.time() - _ollama_down_since if _ollama_down_since else 0.0


@app.get("/api/scenarios", response_model=list[ScenarioInfo])
def scenarios(_u: dict = Depends(viewer)) -> list[ScenarioInfo]:
    return builtin_scenarios()


@app.get("/api/scenario", response_model=ScenarioState)
def scenario_state(_u: dict = Depends(viewer)) -> ScenarioState:
    _need_scenario()
    return store.state()


@app.post("/api/scenario/load", response_model=ScenarioState)
def scenario_load(req: ScenarioLoadRequest, user: dict = Depends(controller)) -> ScenarioState:
    conn = db.get_conn()
    if req.scenario_id:
        try:
            store.load_builtin(req.scenario_id, user["username"])
        except KeyError:
            raise HTTPException(404, f"Scenario {req.scenario_id} not found") from None
        audit.append(conn, actor(user), "load", f"built-in {req.scenario_id}")
        return store.state()
    if req.timetable is None:
        raise HTTPException(422, "Provide scenario_id, or a timetable (and optionally a station)")
    try:
        station = Station.model_validate(req.station) if req.station else store.station
        tti = TimetableIn.model_validate(req.timetable)
    except ValidationError as e:
        raise HTTPException(422, [{"loc": list(x["loc"]), "msg": x["msg"].removeprefix("Value error, ")}
                                  for x in e.errors()]) from None
    assert station is not None
    errs = referential_errors(station, tti)
    if errs:
        raise HTTPException(422, [{"loc": ["timetable"], "msg": m} for m in errs])
    source = req.source or "custom"
    store.set(station, tti.to_timetable(), source, store.now, user["username"])
    audit.append(conn, actor(user), "load", f"{source} · {len(tti.trains)} trains",
                 payload_hash=db.sha256_text(db.canonical_json(req.timetable)))
    return store.state()


@app.post("/api/scenario/reset", response_model=ScenarioState)
def scenario_reset(user: dict = Depends(controller)) -> ScenarioState:
    sid = store.source if store.source in {s.id for s in builtin_scenarios()} else "S1"
    store.load_builtin(sid, user["username"])
    audit.append(db.get_conn(), actor(user), "reset", f"reset to {sid}")
    return store.state()


@app.post("/api/timetable/upload", response_model=UploadResponse)
async def timetable_upload(file: UploadFile = File(...), sheet: Optional[str] = Form(None),
                           user: dict = Depends(controller)) -> UploadResponse:
    _need_scenario()
    data = await file.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise HTTPException(413, "Timetable files are limited to 1 MB")
    assert store.station
    res = parse_upload(file.filename or "", data, store.station, sheet or None, day=store.timetable.day if store.timetable else "Sun")
    audit.append(db.get_conn(), actor(user), "upload",
                 f"{file.filename} · {res.get('sheet') or ''} · "
                 f"{'ok' if 'timetable' in res else 'needs_sheet' if 'needs_sheet' in res else 'errors'}",
                 payload_hash=res["sha256"])
    if "timetable" in res:
        st = store.station.model_copy(update=res.get("settings") or {})
        return UploadResponse(timetable=to_json(res["timetable"]), station=st.model_dump(mode="json"),
                              sha256=res["sha256"], sheet=res.get("sheet"), excluded=res.get("excluded", []))
    if "needs_sheet" in res:
        return UploadResponse(needs_sheet=res["needs_sheet"], sha256=res["sha256"])
    return JSONResponse(status_code=422, content=UploadResponse(errors=res["errors"], sha256=res["sha256"],
                                                                sheet=res.get("sheet")).model_dump())  # type: ignore[return-value]


# ───────────────────────────── validation and planning ─────────────────────────────

def _scheduled_revision() -> Revision:
    assert store.timetable
    return Revision(method="scheduled", assignments=[
        Assignment.assigned(t.id, t.platform, t.arr, t.dep) if t.platform else Assignment.unassigned(t.id, None)
        for t in store.timetable.trains])


@app.post("/api/validate/scheduled", response_model=ValidationReport)
def validate_scheduled(_u: dict = Depends(controller)) -> ValidationReport:
    _need_scenario()
    assert store.station and store.timetable
    rep = validate(store.station, store.timetable, Disruptions(), _scheduled_revision(), None, 0)
    conn = db.get_conn()
    events.emit(conn, "validation", method="scheduled", valid=rep.valid, fault_injected=False)
    for c in rep.conflicts:
        events.emit(conn, "validation", method="scheduled", valid=False, rule=c.code)
    return rep


def _finish(rev: Revision, inp, user: dict, conn) -> RevisionOut:
    """Validate (independently), classify, measure, persist with hash, cache."""
    assert store.station and store.timetable
    applied_rev = Revision(method="applied", assignments=list(inp.applied_plan().values()))
    report = validate(store.station, store.timetable, inp.disruptions, rev, applied_rev, inp.now)
    rev.id = uuid.uuid4().hex[:12]
    assignments = [a.model_dump(mode="json") for a in rev.assignments]
    context = {"now": inp.now, "disruptions": inp.disruptions.model_dump(mode="json"), "affected": rev.affected,
               "widened": rev.widened, "widened_reason": rev.widened_reason, "stages": rev.stages,
               "applied_revision_id": store.applied_revision_id}
    sha = db.insert_revision(conn, rev.id, store.scenario_id, rev.method, assignments, report.model_dump(mode="json"),
                             report.valid, rev.fault_injected, rev.solver_status, rev.solve_ms, context,
                             user["username"])
    out = RevisionOut(revision=rev, validation=report, recovery=recovery_status(rev), metrics=compute_metrics(rev, inp),
                      changes=classify_and_reason(rev, inp), label=LABELS.get(rev.method, rev.method), sha256=sha)
    store.revisions[rev.id] = out
    events.emit(conn, "validation", method=rev.method, valid=report.valid, fault_injected=rev.fault_injected)
    for c in report.conflicts:
        events.emit(conn, "validation", method=rev.method, valid=False, fault_injected=rev.fault_injected, rule=c.code)
    return out


def _run_planners(inp, full: bool, fault: bool) -> list[Revision]:
    revs: list[Revision] = []
    for m in METHODS[:2]:
        r = plan_cpsat_full(inp, m, None) if full else plan_cpsat(inp, m)
        revs.append(r)
    revs.append(plan_greedy_full(inp, None) if full else plan_greedy(inp))
    if full:
        for r in revs:
            r.affected = []
    if fault:
        inject_fault(revs[0], inp.now, inp.station.min_gap)
    return revs


def _plan_response(inp, revs: list[Revision], user: dict, conn) -> PlanResponse:
    outs = []
    for r in revs:
        events.emit(conn, "plan", value=r.solve_ms, method=r.method, solver_status=r.solver_status,
                    fallback=str(r.method == "greedy" and any(x.failed for x in revs)).lower())
        outs.append(_finish(r, inp, user, conn))
    key = [sorted((a.train_id, a.status, a.platform, a.arr, a.dep) for a in r.assignments) for r in revs]
    return PlanResponse(revisions=outs, affected=revs[0].affected, now=inp.now,
                        disruptions=inp.disruptions.summary(), agree=all(k == key[0] for k in key),
                        fault_injected=any(r.fault_injected for r in revs), widened=any(r.widened for r in revs))


@app.post("/api/assign", response_model=PlanResponse)
def assign(req: AssignRequest, user: dict = Depends(controller)) -> PlanResponse:
    """First platform assignment: every train not yet arrived may move (§17)."""
    _need_scenario()
    conn = db.get_conn()
    with LOCK:
        now = to_min(req.now) if req.now else store.now
        store.now = now
        inp = store.plan_input(now)
        resp = _plan_response(inp, _run_planners(inp, full=True, fault=False), user, conn)
    audit.append(conn, actor(user), "plan", f"assign at {req.now or now} · {len(resp.revisions)} revisions")
    return resp


@app.post("/api/disruptions/parse", response_model=ParseResponse)
def disruptions_parse(req: ParseRequest, user: dict = Depends(controller)) -> ParseResponse:
    """Text → proposals. Never mutates the scenario."""
    _need_scenario()
    assert store.station and store.timetable
    ids = [t.id for t in store.timetable.trains]
    norm = normalise(req.text, ids)
    result, path, ms = parse_text(req.text, norm.text, store.station.platform_ids, ids)
    now = to_min(req.now) if req.now else store.now
    ok, rejected, unparsed = validate_proposals(result.get("events", []), result.get("unparsed", []), req.text,
                                                store.station, store.timetable, now, store.plan_input().applied_plan())
    conn = db.get_conn()
    events.emit(conn, "parse", value=ms, path=path, n_events=len(ok), n_rejected=len(rejected))
    for p in rejected:
        events.emit(conn, "parse_reject", reason=p.reason.code if p.reason else "OTHER")
    audit.append(conn, actor(user), "parse", f"{path} · {len(ok)} proposals · {len(rejected)} rejected",
                 payload=req.text)
    return ParseResponse(proposals=ok, rejected=rejected, unparsed=unparsed, parser_path=path, ms=ms)


@app.post("/api/disruptions/transcribe", response_model=TranscribeResponse)
async def disruptions_transcribe(file: UploadFile = File(...), lang: str = Form("en"),
                                 user: dict = Depends(controller)) -> TranscribeResponse:
    """Audio → transcript text only. Never mutates the scenario; the audio is discarded."""
    _need_scenario()
    name = (file.filename or "").lower()
    if not name.endswith(stt.EXTENSIONS):
        raise HTTPException(400, "Only .wav, .mp3 or .webm audio")
    data = await file.read(stt.MAX_BYTES + 1)
    if len(data) > stt.MAX_BYTES:
        raise HTTPException(413, "Audio is limited to 2 MB")
    assert store.station and store.timetable
    t0 = time.monotonic()
    res = stt.transcribe(data, lang, [t.id for t in store.timetable.trains], [p.name for p in store.station.platforms])
    if res.get("error") == "too_long":
        raise HTTPException(413, "Audio is limited to 60 s")
    ms = int((time.monotonic() - t0) * 1000)
    conn = db.get_conn()
    events.emit(conn, "stt", value=ms, path=res["stt_path"])
    audit.append(conn, actor(user), "transcribe", f"{res['stt_path']} · {len(data)} bytes",
                 payload_hash=db.sha256_text(data.hex()))
    return TranscribeResponse(transcript=res["transcript"], stt_path=res["stt_path"], ms=ms, error=res.get("error"))


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest, user: dict = Depends(controller)) -> PlanResponse:
    """Confirmed disruptions → three revisions, each with its own ValidationReport (§5)."""
    _need_scenario()
    conn = db.get_conn()
    now = to_min(req.now)
    new = disruptions_from_in(req.confirmed)
    assert store.timetable and store.station
    tt = store.timetable.by_id()
    applied = store.plan_input().applied_plan()
    for d in new.delays:                                  # the human gate cannot be bypassed by a crafted body
        if d.train_id not in tt:
            raise HTTPException(422, f"{d.train_id} is not in today's timetable")
        a = applied.get(d.train_id)
        arr = a.arr if a and a.arr is not None else tt[d.train_id].arr
        dep = a.dep if a and a.dep is not None else tt[d.train_id].dep
        if dep <= now or (d.kind == "arrival" and arr <= now):
            raise HTTPException(422, f"{d.train_id} has already {'departed' if dep <= now else 'arrived'} at {req.now}")
    for c in new.closures:
        if store.station.platform(c.platform_id) is None:
            raise HTTPException(422, f"{c.platform_id} does not exist")
    with LOCK:
        with db.tx(conn):
            for item in req.confirmed:
                db.insert_disruption(conn, store.scenario_id, item.model_dump(mode="json"), req.source_text or "",
                                     req.parser_path, user["username"])
            if req.confirmed:
                audit.append(conn, actor(user), "confirm", "; ".join(new.summary()), payload=req.source_text or "")
        for item in req.confirmed:
            events.emit(conn, "confirm", type=item.type)
        store.disruptions = store.disruptions.merged(new)
        store.now = now
        inp = store.plan_input(now)
        resp = _plan_response(inp, _run_planners(inp, full=False, fault=req.inject_fault), user, conn)
    audit.append(conn, actor(user), "plan",
                 f"now {req.now} · affected {len(resp.affected)} · "
                 + " · ".join(f"{r.label}:{'VALID' if r.validation.valid else 'NOT VALID'}" for r in resp.revisions)
                 + (" · DEMO fault injected" if resp.fault_injected else ""))
    return resp


@app.get("/api/revisions/{rid}", response_model=RevisionOut)
def revision_get(rid: str, _u: dict = Depends(viewer)) -> RevisionOut:
    ro = store.revisions.get(rid)
    if ro is None:
        raise HTTPException(404, "Unknown revision")
    return ro


@app.post("/api/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest, user: dict = Depends(controller)) -> ExplainResponse:
    """Metrics in, three sentences out; every number checked (§10.2)."""
    rows = []
    for rid in req.revision_ids:
        ro = store.revisions.get(rid)
        if ro is None:
            raise HTTPException(404, f"Unknown revision {rid}")
        rows.append({"label": ro.label, "valid": ro.validation.valid, "conflicts": len(ro.validation.conflicts),
                     "recovery": ro.recovery, "total_hold_min": ro.metrics.total_hold_min,
                     "weighted_delay": ro.metrics.weighted_delay, "platform_changes": ro.metrics.platform_changes,
                     "unassigned": ro.metrics.unassigned, "trains_affected": ro.metrics.trains_affected})
    res = explain_fn(rows, store.disruptions.summary(), req.lang)
    events.emit(db.get_conn(), "explain", path=res["explainer_path"], grounding=res["grounding"])
    return ExplainResponse(**res)


@app.post("/api/revisions/{rid}/apply", response_model=ScenarioState)
def apply(rid: str, user: dict = Depends(controller)) -> ScenarioState:
    """What is applied is exactly what was validated (§31)."""
    conn = db.get_conn()
    row = db.get_revision(conn, rid)
    if row is None:
        raise HTTPException(404, "Unknown revision")

    def refuse(code: str, msg: str):
        audit.append(conn, actor(user), "refused", f"apply {rid}: {code}")
        events.emit(conn, "refused", route="/api/revisions/{rid}/apply", needed_role="valid revision", role=code)
        raise HTTPException(409, f"{code}: {msg}")

    if db.sha256_text(row["assignments_json"]) != row["sha256"]:
        refuse("HASH_MISMATCH", "stored revision differs from the one validated")
    if row["fault_injected"]:
        refuse("FAULT_INJECTED", "demo fault revisions can never be applied")
    if not row["valid"]:
        refuse("NOT_VALID", "the validator reported conflicts")
    if row["scenario_id"] != store.scenario_id:
        refuse("STALE_SCENARIO", "the scenario was reloaded since this revision was planned")
    with LOCK:
        assert store.station and store.timetable
        rev = Revision(method=row["method"], assignments=[Assignment.model_validate(a)
                                                          for a in json.loads(row["assignments_json"])])
        ctx = json.loads(row["context_json"])
        if ctx.get("applied_revision_id") != store.applied_revision_id:
            refuse("STALE_PLAN", "another revision was applied since this one was planned")
        inp = store.plan_input()
        applied_rev = Revision(method="applied", assignments=list(inp.applied_plan().values()))
        report = validate(store.station, store.timetable, store.disruptions, rev, applied_rev, store.now)
        if not report.valid:
            refuse("NO_LONGER_VALID", "the revision is not valid against the current state")
        with db.tx(conn):
            db.insert_applied(conn, store.scenario_id, rid, user["username"])
            audit.append(conn, actor(user), "apply", f"{rid} · {row['method']} · {recovery_status(rev)}",
                         payload_hash=row["sha256"])
        store.applied = rev.assignments
        store.applied_disruptions = Disruptions.model_validate(store.disruptions.model_dump())
        store.applied_revision_id, store.applied_method = rid, row["method"]
    events.emit(conn, "apply", method=row["method"])
    return store.state()


# ───────────────────────────── audit ─────────────────────────────

@app.get("/api/audit")
def audit_list(limit: int = 200, _u: dict = Depends(viewer)) -> list[dict]:
    return audit.entries(db.get_conn(), max(1, min(limit, 1000)))


@app.get("/api/audit/verify", response_model=AuditVerify)
def audit_verify(_u: dict = Depends(admin_only)) -> AuditVerify:
    return AuditVerify(**audit.verify(db.get_conn()))


# ───────────────────────────── auth ─────────────────────────────

def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/", secure=config.secure_cookie())


@app.post("/api/auth/login", response_model=SessionOut)
def auth_login(req: LoginRequest, request: Request, response: Response) -> SessionOut:
    from .auth import client_ip
    token, user = do_login(db.get_conn(), req.username, req.password, client_ip(request))
    _set_cookie(response, token)
    return SessionOut(user=user["username"], role=user["role"], lang=user["lang"])


@app.post("/api/auth/logout", status_code=204)
def auth_logout(request: Request) -> Response:
    from .auth import hash_token
    tok = request.cookies.get(COOKIE)
    if tok:
        db.delete_session(db.get_conn(), hash_token(tok))
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/api/auth/me", response_model=SessionOut)
def auth_me(user: dict = Depends(current_user)) -> SessionOut:
    return SessionOut(user=user["username"], role=user["role"], lang=user["lang"])


@app.patch("/api/auth/me", response_model=SessionOut)
def auth_me_lang(req: LangRequest, user: dict = Depends(current_user)) -> SessionOut:
    """Remember the interface language on the user record (§37)."""
    db.update_user(db.get_conn(), user["id"], lang=req.lang)
    return SessionOut(user=user["username"], role=user["role"], lang=req.lang)


@app.post("/api/auth/accept-invite", response_model=SessionOut)
def auth_accept_invite(req: AcceptInviteRequest) -> SessionOut:
    res = accept_invite(db.get_conn(), req.token, req.password)
    return SessionOut(user=res["user"], role=res["role"])


from .admin import router as admin_router  # noqa: E402  (admin routes need the helpers above)

app.include_router(admin_router)


# ───────────────────────────── single-process demo mode (§39) ─────────────────────────────

if config.serve_web() and config.WEB_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    for sub in ("assets", "locales", "fonts"):
        if (config.WEB_DIST / sub).exists():
            app.mount(f"/{sub}", StaticFiles(directory=config.WEB_DIST / sub), name=sub)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (config.WEB_DIST / path).resolve()
        if path and f.is_file() and config.WEB_DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(config.WEB_DIST / "index.html")       # client-side routing; /api/* matched first
