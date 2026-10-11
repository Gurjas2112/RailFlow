"""Identity and access (SPEC §30).

- Argon2id password hashes (argon2-cffi defaults); verify always runs, against a dummy hash for
  unknown users, so unknown-user and wrong-password responses are identical.
- Opaque server-side sessions: 32 random bytes in the `rf_session` cookie, only SHA-256 stored.
  30 min idle, 8 h absolute. Disabling a user deletes their sessions.
- Lockout: 5 failures per username in 15 min → locked 15 min; 20 per IP in 15 min → 429.
- Roles: viewer < controller; admin is a separate track and cannot parse, plan or apply.
  Every refusal returns 403 and writes a `refused` audit entry and event.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Callable, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from . import audit, db, events

ph = PasswordHasher()
DUMMY = ph.hash("not-a-real-password-railflow")
IDLE, ABSOLUTE = 30 * 60, 8 * 3600
LOCK_WINDOW, USER_FAILS, IP_FAILS = 15 * 60, 5, 20
COOKIE = "rf_session"
ROLES = ("viewer", "controller", "admin")
GENERIC = "Invalid username or password"

_COMMON = {
    "password", "password1", "password12", "password123", "123456789012", "qwertyuiopas", "letmein12345",
    "iloveyou1234", "admin1234567", "welcome12345", "railflow1234", "changeme1234", "passwordpassword",
    "111111111111", "000000000000", "abcdefghijkl", "qwerty123456", "123412341234", "trustno1trustno1",
    "monkey123456", "dragon123456", "football1234", "baseball1234", "sunshine1234", "princess1234",
    "superman1234", "1q2w3e4r5t6y", "zaq12wsxcde3", "asdfghjkl123", "controller12", "viewerviewer",
}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(pw_hash: Optional[str], password: str) -> bool:
    try:
        return ph.verify(pw_hash or DUMMY, password) and pw_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(username: str, password: str) -> Optional[str]:
    """None if acceptable: ≥ 12 chars, not common, not the username (§30)."""
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if password.lower() in _COMMON:
        return "Password is too common"
    if password.lower() == username.lower():
        return "Password must not equal the username"
    return None


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def is_locked(conn, username: str, ip: str) -> bool:
    since = int(time.time()) - LOCK_WINDOW
    return db.recent_failures(conn, username, since) >= USER_FAILS or db.recent_ip_failures(conn, ip, since) >= IP_FAILS


def login(conn, username: str, password: str, ip: str) -> tuple[str, dict]:
    """Returns (token, user) or raises 401/429 with one generic message."""
    if is_locked(conn, username, ip):
        events.emit(conn, "auth", result="locked")
        audit.append(conn, actor=username[:32] or "?", action="login_failed", summary=f"locked · {ip}")
        raise HTTPException(429, "Too many attempts. Try again later.")
    user = db.get_user(conn, username)
    ok = verify_password(user["pw_hash"] if user else None, password)      # always runs Argon2
    if not ok or not user or user["disabled"]:
        db.record_attempt(conn, username, ip, ok=False)
        audit.append(conn, actor=username[:32] or "?", action="login_failed", summary=ip)
        events.emit(conn, "auth", result="fail")
        raise HTTPException(401, GENERIC)
    db.record_attempt(conn, username, ip, ok=True)
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.create_session(conn, hash_token(token), user["id"], created=now, last_seen=now)
    audit.append(conn, actor=f"{username} ({user['role']})", action="login", summary=user["role"])
    events.emit(conn, "auth", result="ok", role=user["role"])
    return token, user


def current_user(request: Request) -> dict:
    conn = db.get_conn()
    tok = request.cookies.get(COOKIE)
    s = db.get_session(conn, hash_token(tok)) if tok else None
    now = int(time.time())
    if not s or s["disabled"] or now - s["last_seen"] > IDLE or now - s["created"] > ABSOLUTE:
        if s:
            db.delete_session_id(conn, s["sid"])
        raise HTTPException(401, "Signed out")
    if now - s["last_seen"] >= 15:
        db.touch_session(conn, s["sid"], now)
    request.state.user = s["username"]
    return {"id": s["id"], "username": s["username"], "role": s["role"], "lang": s["lang"]}


def actor(user: dict) -> str:
    return f"{user['username']} ({user['role']})"


def require_role(*roles: str) -> Callable:
    """Dependency: the signed-in user must hold one of `roles` (admin is never implied)."""
    allowed = set(roles)
    if "viewer" in allowed:
        allowed.add("controller")

    def guard(request: Request, user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed:
            conn = db.get_conn()
            need = "/".join(roles)
            audit.append(conn, actor=actor(user), action="refused",
                         summary=f"{request.method} {request.url.path} needs {need}")
            events.emit(conn, "refused", route=request.url.path, needed_role=need, role=user["role"])
            raise HTTPException(403, f"Requires {need}")
        return user
    return guard


def new_invite(conn, username: str, role: str, created_by: str) -> str:
    token = secrets.token_urlsafe(32)
    db.insert_invite(conn, hash_token(token), username, role, created_by)
    return token


def accept_invite(conn, token: str, password: str) -> dict:
    inv = db.get_invite(conn, hash_token(token))
    if not inv or inv["used_at"] is not None or inv["expires_at"] < int(time.time()):
        raise HTTPException(410, "Invite expired or already used")
    if (problem := password_problem(inv["username"], password)):
        raise HTTPException(422, problem)
    with db.tx(conn):
        if not db.mark_invite_used(conn, hash_token(token)):
            raise HTTPException(410, "Invite expired or already used")
        if db.get_user(conn, inv["username"]):
            raise HTTPException(409, "User already exists")
        db.insert_user(conn, inv["username"], inv["role"], hash_password(password), created_by=inv["created_by"])
        audit.append(conn, actor=f"{inv['username']} ({inv['role']})", action="invite_accepted", summary=inv["role"])
    return {"user": inv["username"], "role": inv["role"]}


