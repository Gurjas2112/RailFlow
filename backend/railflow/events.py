"""Events for the admin dashboard (SPEC §34): emit() and the aggregate queries.

Kinds: plan · validation · parse · explain · apply · auth · refused · http · confirm · stt.
Aggregates are plain SQL over `events` and `revisions` within a time window.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional


def emit(conn: sqlite3.Connection, kind: str, value: float = 1, **labels: Any) -> None:
    try:
        conn.execute("INSERT INTO events (ts, kind, labels, value) VALUES (?, ?, ?, ?)",
                     (int(time.time()), kind, json.dumps({k: str(v) for k, v in labels.items()}, sort_keys=True),
                      float(value)))
    except sqlite3.Error:
        pass                                                   # monitoring must never break a request


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 1)


def _count_by(conn, kind: str, label: str, since: int) -> dict[str, int]:
    rows = conn.execute(f"""SELECT json_extract(labels, '$.{label}') AS k, COUNT(*) AS n FROM events
                            WHERE kind = ? AND ts >= ? GROUP BY k""", (kind, since)).fetchall()
    return {str(r["k"]): r["n"] for r in rows if r["k"] is not None}


def _values(conn, kind: str, since: int, where: str = "", args: tuple = ()) -> list[float]:
    return [r[0] for r in conn.execute(f"SELECT value FROM events WHERE kind = ? AND ts >= ? {where}",
                                       (kind, since, *args))]


def parser_share(conn, since: int) -> dict[str, int]:
    return _count_by(conn, "parse", "path", since)


def invalid_without_fault(conn, since: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM revisions WHERE valid = 0 AND fault_injected = 0 AND created_at >= ?",
                        (since,)).fetchone()[0]


def aggregate(conn: sqlite3.Connection, window_min: int, health: dict[str, Any],
              operations: dict[str, Any], users: list[dict]) -> dict[str, Any]:
    since = int(time.time()) - window_min * 60

    # 2 · planning
    planning: dict[str, Any] = {"methods": [], "status": _count_by(conn, "plan", "solver_status", since)}
    for m in ("cpsat_min_delay", "cpsat_min_changes", "greedy"):
        v = _values(conn, "plan", since, "AND json_extract(labels, '$.method') = ?", (m,))
        planning["methods"].append({"method": m, "n": len(v), "p50": _pct(v, 0.5), "p95": _pct(v, 0.95)})
    planning["greedy_fallbacks"] = conn.execute(
        """SELECT COUNT(*) FROM events WHERE kind = 'plan' AND ts >= ? AND json_extract(labels, '$.fallback') = 'true'""",
        (since,)).fetchone()[0]
    st = planning["status"]
    solved = st.get("OPTIMAL", 0) + st.get("FEASIBLE", 0)
    planning["feasible_share"] = round(st.get("FEASIBLE", 0) / solved, 3) if solved else 0.0

    # 3 · validation
    rv = conn.execute("""SELECT SUM(valid = 1) AS ok, SUM(valid = 0 AND fault_injected = 1) AS fault,
                                SUM(valid = 0 AND fault_injected = 0) AS bad
                         FROM revisions WHERE created_at >= ?""", (since,)).fetchone()
    validation = {"valid": rv["ok"] or 0, "invalid_fault": rv["fault"] or 0, "invalid_without_fault": rv["bad"] or 0,
                  "by_rule": _count_by(conn, "validation", "rule", since)}

    # 4 · AI
    ai = {"parser_share": parser_share(conn, since),
          "parse_p50_ms": _pct(_values(conn, "parse", since, "AND json_extract(labels, '$.path') = 'llm'"), 0.5),
          "rejections": _count_by(conn, "parse_reject", "reason", since),
          "explainer": _count_by(conn, "explain", "path", since),
          "grounding_failures": conn.execute(
              """SELECT COUNT(*) FROM events WHERE kind = 'explain' AND ts >= ?
                 AND json_extract(labels, '$.grounding') = 'failed→template'""", (since,)).fetchone()[0]}

    # 5 · operations (applied plan supplied by the caller) + confirmed disruptions over time
    buckets = conn.execute("""SELECT (confirmed_at / 300) * 300 AS b, COUNT(*) AS n FROM disruptions
                              WHERE confirmed_at >= ? GROUP BY b ORDER BY b""", (since,)).fetchall()
    ops = {**operations, "disruptions_over_time": [{"ts": r["b"], "n": r["n"]} for r in buckets]}

    # 6 · security
    security = {"logins": _count_by(conn, "auth", "result", since),
                "refused_by_role": _count_by(conn, "refused", "role", since),
                "users": users}

    # 1 · health additions
    http_ms = _values(conn, "http", since)
    health = {**health, "api_p95_ms": _pct(http_ms, 0.95), "requests": len(http_ms)}

    five_min = int(time.time()) - 300
    fails_5m = conn.execute("""SELECT COUNT(*) FROM events WHERE kind = 'auth' AND ts >= ?
                               AND json_extract(labels, '$.result') IN ('fail', 'locked')""", (five_min,)).fetchone()[0]
    alerts = []
    if validation["invalid_without_fault"]:
        alerts.append("INVALID_WITHOUT_FAULT")
    if health.get("ollama_down_s", 0) > 60:
        alerts.append("OLLAMA_DOWN")
    if not health.get("audit_intact", True):
        alerts.append("AUDIT_BROKEN")
    if fails_5m >= 3:
        alerts.append("LOGIN_FAILURES")
    if planning["feasible_share"] > 0.2:
        alerts.append("FEASIBLE_SHARE")

    return {"window_min": window_min, "health": health, "planning": planning, "validation": validation,
            "ai": ai, "operations": ops, "security": security, "alerts": alerts}
