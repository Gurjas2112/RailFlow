"""Shared local-Ollama settings (SPEC §10, §27). Ollama is never exposed beyond localhost.

Model: RAILFLOW_OLLAMA_MODEL if set, otherwise the first installed model from PREFERRED.
`qwen2.5:3b` and `qwen2.5:3b-instruct` are the same weights under different tags.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

OLLAMA = (os.getenv("RAILFLOW_OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
PREFERRED = ["qwen2.5:3b", "qwen2.5:3b-instruct", "qwen2.5:7b-instruct", "llama3.2:latest"]
TIMEOUT = 8.0

_cache: tuple[float, Optional[str], bool] = (0.0, None, False)


def _probe() -> tuple[Optional[str], bool]:
    global _cache
    ts, name, up = _cache
    if time.monotonic() - ts < 30:
        return name, up
    try:
        tags = httpx.get(f"{OLLAMA}/api/tags", timeout=1.5).json().get("models", [])
        have = {m.get("name") for m in tags}
        forced = os.getenv("RAILFLOW_OLLAMA_MODEL") or os.getenv("RAILFLOW_LLM_MODEL")
        name = forced if forced else next((p for p in PREFERRED if p in have), None)
        up = True
    except Exception:
        name, up = None, False
    _cache = (time.monotonic(), name, up)
    return name, up


def resolve_model() -> Optional[str]:
    """Installed model name, or None if Ollama is down or has none of PREFERRED. Cached 30 s."""
    return _probe()[0]


def ollama_up() -> bool:
    return _probe()[1]


def reset_cache() -> None:
    global _cache
    _cache = (0.0, None, False)


def chat(system: str, user: str, schema: Optional[dict] = None, timeout: float = TIMEOUT) -> Optional[str]:
    """One deterministic chat call (temperature 0). Returns the message text, or None on any failure."""
    model = resolve_model()
    if not model:
        return None
    body: dict[str, Any] = {
        "model": model, "stream": False, "options": {"temperature": 0, "seed": 42},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if schema is not None:
        body["format"] = schema
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception:
        return None
