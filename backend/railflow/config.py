"""Paths and environment (SPEC §33). Reads `<repo>/.env` once without overriding real env vars.

`.env` is gitignored; `.env.example` lists every key with no values.
"""
from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LOGS = ROOT / "logs"
WEB_DIST = ROOT / "web" / "dist"
LOCALES = ROOT / "web" / "public" / "locales"


def load_env(path: pathlib.Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


load_env()


def env(name: str, default: str = "") -> str:
    return os.getenv(name) or default


def db_path() -> pathlib.Path:
    p = env("RAILFLOW_DB")
    return pathlib.Path(p) if p else DATA / "railflow.db"


def allowed_origins() -> set[str]:
    raw = env("RAILFLOW_ALLOWED_ORIGINS",
              "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def serve_web() -> bool:
    return env("RAILFLOW_SERVE_WEB") == "1"


def secure_cookie() -> bool:
    return env("RAILFLOW_SECURE_COOKIE") == "1"
