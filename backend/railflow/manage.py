"""RailFlow management CLI (SPEC §28, §30, §31). Idempotent; no default credentials exist in code.

    python -m railflow.manage init-db
    python -m railflow.manage create-admin [username]        # prompts for the password
    python -m railflow.manage seed-demo                      # viewer · controller · admin, passwords from .env
    python -m railflow.manage unlock <username>
    python -m railflow.manage backup                         # data/backups/railflow-<ts>.db
"""
from __future__ import annotations

import getpass
import os
import sqlite3
import sys
import time

from . import audit, config, db
from .auth import hash_password, password_problem

DEMO = [("viewer", "viewer", "RAILFLOW_VIEWER_PASSWORD"),
        ("controller", "controller", "RAILFLOW_CONTROLLER_PASSWORD"),
        ("admin", "admin", "RAILFLOW_ADMIN_PASSWORD")]


def init_db() -> None:
    db.init_db()
    print(f"database ready: {db.DB_PATH} · integrity {db.integrity_check()}")


def _create(username: str, role: str, password: str, by: str) -> bool:
    conn = db.get_conn()
    if db.get_user(conn, username):
        print(f"  {username}: exists, unchanged")
        return False
    if (problem := password_problem(username, password)):
        raise SystemExit(f"  {username}: {problem}")
    db.insert_user(conn, username, role, hash_password(password), created_by=by)
    audit.append(conn, by, "user_created", f"{username} as {role}")
    print(f"  {username}: created ({role})")
    return True


def create_admin(username: str = "admin") -> None:
    init_db()
    pw = os.getenv("RAILFLOW_NEW_ADMIN_PASSWORD") or getpass.getpass(f"Password for {username} (min 12 chars): ")
    _create(username, "admin", pw, "manage.py")


def seed_demo() -> None:
    init_db()
    missing = [env for _, _, env in DEMO if not os.getenv(env)]
    if missing:
        raise SystemExit("set these in .env first (see .env.example): " + ", ".join(missing))
    for username, role, env in DEMO:
        _create(username, role, os.environ[env], "manage.py seed-demo")


def unlock(username: str) -> None:
    db.clear_failures(db.get_conn(), username)
    audit.append(db.get_conn(), "manage.py", "user_changed", f"{username}: unlocked")
    print(f"{username}: unlocked")


def backup() -> None:
    dest_dir = config.DATA / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"railflow-{time.strftime('%Y%m%d-%H%M%S')}.db"
    out = sqlite3.connect(str(dest))
    with out:
        db.get_conn().backup(out)
    out.close()
    print(f"backup written: {dest}")


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        raise SystemExit(1)
    cmd, rest = argv[0], argv[1:]
    if cmd == "init-db":
        init_db()
    elif cmd == "create-admin":
        create_admin(rest[0] if rest else "admin")
    elif cmd == "seed-demo":
        seed_demo()
    elif cmd == "unlock" and rest:
        unlock(rest[0])
    elif cmd == "backup":
        backup()
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
