"""Admin routes (SPEC §17, §30, §34): users, invites and the Operations & System Health dashboard.

Admin only. An admin manages accounts and watches the system; an admin cannot parse, plan or apply.
The last active admin can never be demoted or disabled.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from . import audit, db, events
from .auth import actor, new_invite, require_role
from .models import InviteOut, InviteRequest, UserOut, UserPatch
from .scenario_store import store

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_role("admin")


def _user_out(u: dict) -> UserOut:
    return UserOut(id=u["id"], username=u["username"], role=u["role"], disabled=bool(u["disabled"]),
                   lang=u.get("lang") or "en")


@router.get("/users", response_model=list[UserOut])
def users(_u: dict = Depends(admin_only)) -> list[UserOut]:
    return [_user_out(u) for u in db.list_users(db.get_conn())]


@router.post("/users/invite", response_model=InviteOut)
def invite(req: InviteRequest, user: dict = Depends(admin_only)) -> InviteOut:
    conn = db.get_conn()
    if db.get_user(conn, req.username):
        raise HTTPException(409, f"User {req.username} already exists")
    token = new_invite(conn, req.username, req.role, user["username"])
    audit.append(conn, actor(user), "user_invited", f"{req.username} as {req.role}")
    return InviteOut(username=req.username, role=req.role, token=token, link=f"/invite/{token}")


@router.patch("/users/{ref}", response_model=UserOut)
def patch_user(ref: str, req: UserPatch, user: dict = Depends(admin_only)) -> UserOut:
    """`ref` is a user id or a username."""
    conn = db.get_conn()
    target = db.get_user_by_id(conn, int(ref)) if ref.isdigit() else db.get_user(conn, ref)
    if not target:
        raise HTTPException(404, "User not found")
    losing_admin = target["role"] == "admin" and not target["disabled"] and (
        (req.role is not None and req.role != "admin") or req.disabled is True)
    if losing_admin and db.count_active_admins(conn) <= 1:
        raise HTTPException(409, "The last admin cannot be demoted or disabled")
    changes = {}
    with db.tx(conn):
        if req.role is not None and req.role != target["role"]:
            changes["role"] = req.role
        if req.disabled is not None and bool(req.disabled) != bool(target["disabled"]):
            changes["disabled"] = 1 if req.disabled else 0
        if changes:
            db.update_user(conn, target["id"], **changes)
            if changes.get("disabled") or "role" in changes:
                db.delete_user_sessions(conn, target["id"])        # next request returns 401
            audit.append(conn, actor(user), "user_changed", f"{target['username']}: {changes}")
    fresh = db.get_user_by_id(conn, target["id"])
    assert fresh
    return _user_out(fresh)


@router.get("/metrics")
def metrics(window: int = 60, _u: dict = Depends(admin_only)) -> dict:
    """Dashboard aggregates over the last `window` minutes (§34)."""
    from .main import health, ollama_down_seconds
    conn = db.get_conn()
    h = health()
    v = audit.verify(conn)
    health_panel = {"api": "up", "ollama": h.ollama, "model": h.model, "db": h.db, "db_bytes": db.size_bytes(),
                    "audit_intact": v["intact"], "audit_entries": v["entries"], "first_broken_seq": v["first_broken_seq"],
                    "validator_version": h.validator_version, "stt": h.stt, "ollama_down_s": round(ollama_down_seconds())}
    users = [_user_out(u).model_dump() for u in db.list_users(conn)]
    return events.aggregate(conn, max(1, min(window, 24 * 60)), health_panel, store.utilisation(), users)
