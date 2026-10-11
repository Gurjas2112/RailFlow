"""SHA-256 hash-chained audit log (SPEC §12).

Append-only `audit` table, protected by UPDATE/DELETE-blocking triggers. Each entry:
seq, ts, actor (username + role), action, payload_hash, summary, prev_hash, hash with
hash = SHA-256(prev_hash ‖ canonical_json(entry_without_hash)). verify() walks the chain and
returns the first broken seq. The triggers stop accidental edits; the chain catches deliberate ones.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any, Optional

ACTIONS = {"login", "login_failed", "logout", "parse", "confirm", "plan", "apply", "refused", "reset",
           "load", "upload", "user_invited", "user_changed", "user_created", "invite_accepted", "transcribe"}
GENESIS = "0" * 64


def _canonical(entry: dict) -> str:
    return json.dumps({k: entry[k] for k in sorted(entry) if k not in ("hash", "seq")},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()


def append(conn: sqlite3.Connection, actor: str, action: str, summary: str = "",
           payload: Optional[str] = None, payload_hash: Optional[str] = None) -> int:
    """Append one entry. `payload` is hashed; pass `payload_hash` when the hash is already known."""
    if payload_hash is None and payload is not None:
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if not conn.in_transaction:                      # BEGIN IMMEDIATE serialises writers on the chain head
        from .db import tx
        with tx(conn):
            return _insert(conn, actor, action, summary, payload_hash)
    return _insert(conn, actor, action, summary, payload_hash)


def _insert(conn: sqlite3.Connection, actor: str, action: str, summary: str, payload_hash: Optional[str]) -> int:
    row = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row[0] if row else GENESIS
    e = {"ts": int(time.time()), "actor": actor, "action": action,
         "payload_hash": payload_hash, "summary": summary[:2000], "prev_hash": prev}
    cur = conn.execute("""INSERT INTO audit (ts, actor, action, payload_hash, summary, prev_hash, hash)
                          VALUES (?, ?, ?, ?, ?, ?, ?)""",
                       (e["ts"], actor, action, payload_hash, e["summary"], prev, entry_hash(prev, e)))
    return int(cur.lastrowid or 0)


def verify(conn: sqlite3.Connection) -> dict[str, Any]:
    """{intact, entries, first_broken_seq}."""
    prev = GENESIS
    n = 0
    for r in conn.execute("SELECT seq, ts, actor, action, payload_hash, summary, prev_hash, hash FROM audit ORDER BY seq"):
        n += 1
        e = {"ts": r["ts"], "actor": r["actor"], "action": r["action"], "payload_hash": r["payload_hash"],
             "summary": r["summary"], "prev_hash": r["prev_hash"]}
        if r["prev_hash"] != prev or entry_hash(r["prev_hash"], e) != r["hash"]:
            total = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            return {"intact": False, "entries": total, "first_broken_seq": r["seq"]}
        prev = r["hash"]
    return {"intact": True, "entries": n, "first_broken_seq": None}


def entries(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT seq, ts, actor, action, payload_hash, summary, hash FROM audit ORDER BY seq DESC LIMIT ?", (limit,))]


def last(conn: sqlite3.Connection) -> Optional[dict]:
    r = conn.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    return dict(r) if r else None
