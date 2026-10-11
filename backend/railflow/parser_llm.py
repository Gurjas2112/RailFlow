"""LLM parser — free text → proposed disruptions via local Ollama (SPEC §10.1, §37, §43).

JSON-schema-constrained output, temperature 0, 8 s timeout. Falls back to the regex parser
(on the normalised text) when Ollama is unreachable, slow, or returns schema-invalid JSON.
The output can only be delay or closure events: no field can express a platform assignment.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from . import llm
from .parser_regex import parse_regex

SYSTEM_PROMPT = """You extract railway disruption events from an operator's message.
Return ONLY JSON matching the schema. Do not invent events.
Event types: "delay" (train_id, minutes, kind) and "closure" (platform, start, end in HH:MM 24h).
kind is "departure" when the train is at a platform and will leave late ("departure delayed", "held at platform", "will leave late", "प्रस्थान देरी", "सुटण्यास उशीर"); otherwise "arrival" ("running late", "delayed").
Copy train numbers exactly as written. Copy platform references exactly as written.
"source" must be an exact substring of the message.
Put any sentence that is not a delay or closure into "unparsed".
If a time or number is ambiguous, still extract it and set "ambiguous": true.
The message may be in English, Hindi, Marathi or a mix. Train numbers and times may use Devanagari digits; copy them exactly."""

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["delay", "closure"]},
                    "train_id": {"type": "string"},
                    "minutes": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["arrival", "departure"]},
                    "platform": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "source": {"type": "string"},
                    "ambiguous": {"type": "boolean"},
                },
                "required": ["type", "source"],
            },
        },
        "unparsed": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["events", "unparsed"],
}


def _schema_ok(obj: Any) -> bool:
    if not isinstance(obj, dict) or not isinstance(obj.get("events"), list):
        return False
    for e in obj["events"]:
        if not isinstance(e, dict) or e.get("type") not in ("delay", "closure") or not isinstance(e.get("source"), str):
            return False
    obj.setdefault("unparsed", [])
    return isinstance(obj["unparsed"], list)


def call_llm(text: str, platforms: list[str], trains: list[str]) -> Optional[dict[str, Any]]:
    user = (f"Platforms at this station: {', '.join(platforms)}.\n"
            f"Train numbers in today's timetable: {', '.join(trains)}.\n\nMessage:\n{text}")
    raw = llm.chat(SYSTEM_PROMPT, user, SCHEMA)
    if raw is None:
        return None
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if _schema_ok(obj) else None


def parse(text: str, normalised_text: str, platforms: list[str], trains: list[str],
          use_llm: bool = True) -> tuple[dict[str, Any], str, int]:
    """Returns (result, parser_path, ms) with parser_path "llm" or "regex"."""
    t0 = time.monotonic()
    result = call_llm(text, platforms, trains) if use_llm else None
    if result is not None:
        return result, "llm", int((time.monotonic() - t0) * 1000)
    result = parse_regex(normalised_text)
    return result, "regex", int((time.monotonic() - t0) * 1000)


def parse_llm(text: str) -> tuple[dict[str, Any], str, int]:
    """Back-compatible single-argument entry point."""
    return parse(text, text, [], [])
