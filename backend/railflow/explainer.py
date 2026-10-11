"""Trade-off explainer — numbers in, plain language out, numbers checked (SPEC §10.2, §37).

The explainer sees only computed metrics. Every number and HH:MM token in the LLM text must
appear in the metrics input, or the text is replaced by the template. Hindi and Marathi
always use the localised template (grounded by construction): the response carries the
template as `{code, params}` parts that the browser renders in the chosen language.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from . import llm
from .models import ReasonPart

EXPLAIN_SYSTEM = (
    "Explain in at most 3 sentences, for a station controller, the trade-off between these revisions. "
    "Use only numbers present in the input. Do not recommend platform assignments."
)
EXPLAIN_CODES = ["EXPLAIN_AGREE", "EXPLAIN_REVISION", "EXPLAIN_ALL_PLACED", "EXPLAIN_UNPLACED",
                 "EXPLAIN_INVALID", "EXPLAIN_SINGLE"]
_NUM = re.compile(r"\d{1,2}:\d{2}|\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    out = set()
    for tok in _NUM.findall(text):
        out.add(tok if ":" in tok else str(float(tok)).rstrip("0").rstrip("."))
    return out


def grounded(text: str, metrics_input: str) -> bool:
    """True iff every number in `text` occurs in `metrics_input`."""
    return numbers_in(text) <= numbers_in(metrics_input)


def _same(a: dict, b: dict) -> bool:
    keys = ("total_hold_min", "weighted_delay", "platform_changes", "unassigned")
    return all(a.get(k) == b.get(k) for k in keys)


def template_parts(revisions: list[dict[str, Any]]) -> list[ReasonPart]:
    parts: list[ReasonPart] = []
    valid = [r for r in revisions if r.get("valid")]
    for r in revisions:
        if not r.get("valid"):
            parts.append(ReasonPart(code="EXPLAIN_INVALID", params={"label": r.get("label", ""),
                                                                     "conflicts": r.get("conflicts", 0)}))
    if len(valid) >= 2 and all(_same(valid[0], r) for r in valid[1:]):
        r = valid[0]
        parts.append(ReasonPart(code="EXPLAIN_AGREE", params={
            "n": len(valid), "changes": r.get("platform_changes", 0), "hold": r.get("total_hold_min", 0),
            "weighted": r.get("weighted_delay", 0)}))
    else:
        for r in valid:
            parts.append(ReasonPart(code="EXPLAIN_REVISION", params={
                "label": r.get("label", ""), "changes": r.get("platform_changes", 0),
                "hold": r.get("total_hold_min", 0), "weighted": r.get("weighted_delay", 0)}))
    unplaced = max((r.get("unassigned", 0) for r in valid), default=0)
    if valid:
        parts.append(ReasonPart(code="EXPLAIN_ALL_PLACED") if unplaced == 0
                     else ReasonPart(code="EXPLAIN_UNPLACED", params={"n": unplaced}))
    return parts


def render_en(parts: list[ReasonPart]) -> str:
    s: list[str] = []
    for p in parts:
        q = p.params
        s.append({
            "EXPLAIN_AGREE": lambda: (f"All {q['n']} revisions agree: {q['changes']} platform changes, "
                                      f"{q['hold']} min total hold, weighted delay {q['weighted']}."),
            "EXPLAIN_REVISION": lambda: (f"Revision {q['label']} moves {q['changes']} trains and holds trains for "
                                         f"{q['hold']} min in total (weighted delay {q['weighted']})."),
            "EXPLAIN_ALL_PLACED": lambda: "Every train is placed.",
            "EXPLAIN_UNPLACED": lambda: f"{q['n']} trains cannot be placed within the hold limit.",
            "EXPLAIN_INVALID": lambda: f"Revision {q['label']} is NOT VALID ({q['conflicts']} conflicts) and cannot be applied.",
            "EXPLAIN_SINGLE": lambda: "",
        }[p.code]())
    return " ".join(x for x in s if x)


def explain(revisions: list[dict[str, Any]], disruptions: list[str], lang: str = "en",
            chat: Optional[Callable[[str, str], Optional[str]]] = None) -> dict[str, Any]:
    """Returns {text, explainer_path, grounding, parts}."""
    parts = template_parts(revisions)
    template = {"text": render_en(parts), "explainer_path": "template", "grounding": "passed", "parts": parts}
    if lang != "en":
        return template
    metrics_input = json.dumps({"revisions": revisions, "disruptions": disruptions}, ensure_ascii=False, sort_keys=True)
    call = chat or (lambda system, user: llm.chat(system, user))
    text = call(EXPLAIN_SYSTEM, metrics_input)
    if not text or not text.strip():
        return template
    text = text.strip()
    if not grounded(text, metrics_input):
        return {**template, "grounding": "failed→template"}
    return {"text": text, "explainer_path": "llm", "grounding": "passed", "parts": []}
