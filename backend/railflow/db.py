"""SQLite storage (SPEC §31). Built-in sqlite3, parameterised SQL only, no ORM.

One file (`data/railflow.db`, or RAILFLOW_DB), WAL, foreign keys, busy_timeout 5000.
Connections are per thread and in autocommit mode; multi-statement writes use `tx()`.
`STATUS` is set at startup from `PRAGMA integrity_check` and the audit chain; while it is not
"ok", /api/health reports it and every other API route returns 503.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterator, Optional

from . import config

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema.sql"
DB_PATH: pathlib.Path = config.db_path()
STATUS: str = "ok"                      # ok | integrity_failed | audit_broken

_local = threading.local()
_all: list[sqlite3.Connection] = []
_lock = threading.Lock()
_gen = 0


def _open(path: pathlib.Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=5.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 5000")
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


def get_conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "gen", -1) != _gen:
        c = _open(DB_PATH)
        _local.conn, _local.gen = c, _gen
        with _lock:
            _all.append(c)
    return c


def conn() -> sqlite3.Connection:
    """FastAPI dependency."""
    return get_conn()


def set_path(path: pathlib.Path | str) -> None:
    """Point the module at another file (tests, RAILFLOW_DB). Closes every open connection."""
    global DB_PATH, _gen, STATUS
    close_all()
    DB_PATH = pathlib.Path(path)
    _gen += 1
    STATUS = "ok"


def close_all() -> None:
    global _gen
    with _lock:
        for c in _all:
            with contextlib.suppress(Exception):
                c.close()
        _all.clear()
    _gen += 1


@contextlib.contextmanager
def tx(c: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One write transaction: all statements commit together or none do."""
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    c.execute("COMMIT")


def init_db(c: Optional[sqlite3.Connection] = None) -> None:
    (c or get_conn()).executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def integrity_check(c: Optional[sqlite3.Connection] = None) -> str:
    try:
        row = (c or get_conn()).execute("PRAGMA integrity_check").fetchone()
        return row[0] if row else "unknown"
    except sqlite3.DatabaseError as e:
        return f"error: {e}"


def startup() -> str:
    """Schema, integrity check and audit-chain verification before requests are accepted."""
    global STATUS
    from . import audit
    try:
        c = get_conn()
        if integrity_check(c) != "ok":
            STATUS = "integrity_failed"
            return STATUS
        init_db(c)
        STATUS = "ok" if audit.verify(c)["intact"] else "audit_broken"
    except sqlite3.DatabaseError:
        STATUS = "integrity_failed"
    return STATUS


def size_bytes() -> int:
    try:
        return sum(p.stat().st_size for p in DB_PATH.parent.glob(DB_PATH.name + "*") if p.is_file())
    except OSError:
        return 0


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_s() -> int:
    return int(time.time())


def _one(c: sqlite3.Connection, sql: str, args: tuple = ()) -> Optional[dict]:
    row = c.execute(sql, args).fetchone()
    return dict(row) if row else None


# ─── users ───

def get_user(c, username: str) -> Optional[dict]:
    return _one(c, "SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(c, uid: int) -> Optional[dict]:
    return _one(c, "SELECT * FROM users WHERE id = ?", (uid,))


def insert_user(c, username: str, role: str, pw_hash: str, created_by: Optional[str] = None) -> int:
    cur = c.execute("INSERT INTO users (username, pw_hash, role, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                    (username, pw_hash, role, now_s(), created_by))
    return int(cur.lastrowid)


def update_user(c, uid: int, **fields: Any) -> None:
    allowed = {"role", "disabled", "pw_hash", "lang"}
    for k, v in fields.items():
        if k in allowed:                                   # column names from a fixed allowlist
            c.execute(f"UPDATE users SET {k} = ? WHERE id = ?", (v, uid))


def list_users(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT id, username, role, disabled, lang, created_at, created_by FROM users ORDER BY id")]


def count_active_admins(c) -> int:
    return c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0").fetchone()[0]


# ─── sessions ───

def create_session(c, token_hash: str, uid: int, created: int, last_seen: int) -> None:
    c.execute("INSERT INTO sessions (token_hash, user_id, created, last_seen) VALUES (?, ?, ?, ?)",
              (token_hash, uid, created, last_seen))


def get_session(c, token_hash: str) -> Optional[dict]:
    return _one(c, """SELECT s.id AS sid, s.created, s.last_seen, u.id, u.username, u.role, u.disabled, u.lang
                      FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""", (token_hash,))


def touch_session(c, sid: int, ts: int) -> None:
    c.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (ts, sid))


def delete_session(c, token_hash: str) -> None:
    c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_session_id(c, sid: int) -> None:
    c.execute("DELETE FROM sessions WHERE id = ?", (sid,))


def delete_user_sessions(c, uid: int) -> None:
    c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))


# ─── login attempts ───

def record_attempt(c, username: str, ip: str, ok: bool) -> None:
    c.execute("INSERT INTO login_attempts (ts, username, ip, ok) VALUES (?, ?, ?, ?)",
              (now_s(), username, ip, 1 if ok else 0))


def recent_failures(c, username: str, since: int) -> int:
    return c.execute("SELECT COUNT(*) FROM login_attempts WHERE username = ? AND ok = 0 AND ts >= ?",
                     (username, since)).fetchone()[0]


def recent_ip_failures(c, ip: str, since: int) -> int:
    return c.execute("SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND ok = 0 AND ts >= ?",
                     (ip, since)).fetchone()[0]


def clear_failures(c, username: str) -> None:
    """`manage.py unlock`: failures are kept for the record but no longer count."""
    c.execute("UPDATE login_attempts SET ok = 2 WHERE username = ? AND ok = 0", (username,))


# ─── invites ───

def insert_invite(c, token_hash: str, username: str, role: str, created_by: str, ttl: int = 86400) -> None:
    c.execute("INSERT INTO invites (token_hash, username, role, expires_at, created_by) VALUES (?, ?, ?, ?, ?)",
              (token_hash, username, role, now_s() + ttl, created_by))


def get_invite(c, token_hash: str) -> Optional[dict]:
    return _one(c, "SELECT * FROM invites WHERE token_hash = ?", (token_hash,))


def mark_invite_used(c, token_hash: str) -> bool:
    cur = c.execute("UPDATE invites SET used_at = ? WHERE token_hash = ? AND used_at IS NULL", (now_s(), token_hash))
    return cur.rowcount == 1


def list_invites(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT username, role, expires_at, used_at, created_by FROM invites ORDER BY expires_at DESC")]


# ─── scenarios ───

def insert_scenario(c, station: Any, timetable: Any, loaded_by: str, source: str = "") -> str:
    sj, tj = canonical_json(station), canonical_json(timetable)
    sid = uuid.uuid4().hex[:12]
    c.execute("""INSERT INTO scenarios (id, station_json, timetable_json, sha256, source, loaded_by, loaded_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""", (sid, sj, tj, sha256_text(sj + tj), source, loaded_by, now_s()))
    return sid


def get_scenario(c, sid: str) -> Optional[dict]:
    return _one(c, "SELECT * FROM scenarios WHERE id = ?", (sid,))


# ─── disruptions ───

def insert_disruption(c, scenario_id: str, obj: Any, source_text: str, parser_path: str, confirmed_by: str) -> None:
    c.execute("""INSERT INTO disruptions (scenario_id, json, source_text, parser_path, confirmed_by, confirmed_at)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (scenario_id, canonical_json(obj), source_text, parser_path, confirmed_by, now_s()))


def list_disruptions(c, scenario_id: str) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT * FROM disruptions WHERE scenario_id = ? ORDER BY confirmed_at, id", (scenario_id,))]


# ─── revisions ───

def insert_revision(c, rid: str, scenario_id: str, method: str, assignments: Any, validation: Any,
                    valid: bool, fault_injected: bool, solver_status: str, solve_ms: int,
                    context: Any, created_by: str) -> str:
    aj = canonical_json(assignments)
    sha = sha256_text(aj)
    c.execute("""INSERT INTO revisions (id, scenario_id, method, assignments_json, sha256, validation_json, valid,
                 fault_injected, solver_status, solve_ms, context_json, created_by, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (rid, scenario_id, method, aj, sha, canonical_json(validation), 1 if valid else 0,
               1 if fault_injected else 0, solver_status, solve_ms, canonical_json(context), created_by, now_s()))
    return sha


def get_revision(c, rid: str) -> Optional[dict]:
    return _one(c, "SELECT * FROM revisions WHERE id = ?", (rid,))


# ─── applied ───

def insert_applied(c, scenario_id: str, revision_id: str, applied_by: str) -> int:
    cur = c.execute("INSERT INTO applied (scenario_id, revision_id, applied_by, applied_at) VALUES (?, ?, ?, ?)",
                    (scenario_id, revision_id, applied_by, now_s()))
    return int(cur.lastrowid)


def current_applied(c, scenario_id: str) -> Optional[dict]:
    return _one(c, """SELECT r.*, a.applied_by, a.applied_at FROM applied a JOIN revisions r ON r.id = a.revision_id
                      WHERE a.scenario_id = ? ORDER BY a.seq DESC LIMIT 1""", (scenario_id,))
