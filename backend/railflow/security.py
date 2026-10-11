"""Security controls (SPEC §32 layer 1, §33).

- CSP `default-src 'self'` and the other headers on every response; `Cache-Control: no-store` on /api/*
- Origin allowlist on every non-GET request (second CSRF layer after SameSite=Strict); in
  single-process demo mode the app is same-origin, so the request's own host is also allowed
- Body limits: 256 KB JSON, 1 MB timetable upload, 2 MB audio → 413
- While the database is not healthy, every /api route except /api/health returns 503
- Structured JSON-lines request log in logs/railflow.log with a redaction filter
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import config, db, events

MAX_BODY = 256 * 1024
LIMITS = {"/api/timetable/upload": 1024 * 1024 + 16 * 1024, "/api/disruptions/transcribe": 2 * 1024 * 1024 + 16 * 1024}
REDACT = {"password", "token", "rf_session", "pw_hash", "cookie", "authorization"}
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; font-src 'self' data:; worker-src 'self' blob:; frame-ancestors 'none'")


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[redacted]" if k.lower() in REDACT else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = record.msg if isinstance(record.msg, dict) else {"msg": record.getMessage()}
        return json.dumps(redact({"ts": round(record.created, 3), "level": record.levelname, **payload}),
                          ensure_ascii=False)


def get_logger() -> logging.Logger:
    log = logging.getLogger("railflow")
    if not log.handlers:
        log.setLevel(logging.INFO)
        log.propagate = False
        try:
            config.LOGS.mkdir(parents=True, exist_ok=True)
            h: logging.Handler = logging.FileHandler(config.LOGS / "railflow.log", encoding="utf-8")
        except OSError:
            h = logging.NullHandler()
        h.setFormatter(RedactingFormatter())
        log.addHandler(h)
    return log


def _origin_ok(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True                                   # non-browser client; SameSite=Strict still applies
    origin = origin.rstrip("/")
    if origin in config.allowed_origins():
        return True
    host = request.headers.get("host", "")
    return config.serve_web() and origin in (f"http://{host}", f"https://{host}")


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        t0 = time.monotonic()
        path = request.url.path
        rid = uuid.uuid4().hex[:8]
        if path.startswith("/api/") and path != "/api/health" and db.STATUS != "ok":
            resp: Response = JSONResponse({"detail": f"Database {db.STATUS}; writes refused"}, status_code=503)
        elif request.method not in ("GET", "HEAD", "OPTIONS") and not _origin_ok(request):
            resp = JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        elif int(request.headers.get("content-length") or 0) > LIMITS.get(path, MAX_BODY):
            resp = JSONResponse({"detail": "Request too large"}, status_code=413)
        else:
            resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        if path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
            ms = (time.monotonic() - t0) * 1000
            route = request.scope.get("route")
            route_path = getattr(route, "path", path)
            if db.STATUS == "ok" and route_path != "/api/admin/metrics":
                events.emit(db.get_conn(), "http", value=round(ms, 1), route=route_path, status=resp.status_code)
            get_logger().info({"rid": rid, "method": request.method, "route": route_path,
                               "status": resp.status_code, "ms": round(ms, 1),
                               "user": getattr(request.state, "user", None)})
        return resp
