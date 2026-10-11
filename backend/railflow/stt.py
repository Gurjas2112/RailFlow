"""Local speech-to-text for radio reports (SPEC §41) — optional, Tier 3.

faster-whisper `small` on the CPU with int8, enabled by RAILFLOW_STT=1 and only if the package is
installed. The transcript is operator text and nothing more: it lands in the Disruption box,
editable, and goes through the same parser, proposal validator and confirmation. The audio is
decoded in memory and discarded. On any failure the result says `unavailable`.
"""
from __future__ import annotations

import io
import os
import threading
from typing import Any, Callable, Optional

MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 60
EXTENSIONS = (".wav", ".mp3", ".webm")
LANGS = {"en": "en", "hi": "hi", "mr": "mr"}

_model: Any = None
_lock = threading.Lock()
_factory: Optional[Callable[[], Any]] = None          # tests inject a fake model here


def enabled() -> bool:
    if _factory is not None:
        return True
    if os.getenv("RAILFLOW_STT") != "1":
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> str:
    return "whisper-small" if enabled() else "unavailable"


def _get() -> Any:
    global _model
    with _lock:
        if _model is None:
            if _factory is not None:
                _model = _factory()
            else:
                from faster_whisper import WhisperModel
                _model = WhisperModel("small", device="cpu", compute_type="int8")
        return _model


def set_factory(f: Optional[Callable[[], Any]]) -> None:
    global _model, _factory
    _factory, _model = f, None


def vocabulary(train_ids: list[str], platform_names: list[str]) -> str:
    return ", ".join(train_ids[:30] + platform_names + ["platform", "minutes late", "closed", "departure"])


def transcribe(data: bytes, lang: str, train_ids: list[str], platform_names: list[str]) -> dict[str, Any]:
    if not enabled():
        return {"transcript": "", "stt_path": "unavailable", "error": "speech-to-text is not installed or not enabled"}
    try:
        segs, info = _get().transcribe(io.BytesIO(data), language=LANGS.get(lang, "en"), beam_size=5,
                                       vad_filter=True, temperature=0,
                                       initial_prompt=vocabulary(train_ids, platform_names))
        duration = float(getattr(info, "duration", 0) or 0)
        if duration > MAX_SECONDS:
            return {"transcript": "", "stt_path": "unavailable", "error": "too_long"}
        text = " ".join(s.text.strip() for s in segs).strip()
        return {"transcript": text, "stt_path": "whisper-small"}
    except Exception as e:                               # the controller types it instead
        return {"transcript": "", "stt_path": "unavailable", "error": str(e)[:200]}
