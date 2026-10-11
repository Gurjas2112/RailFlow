"""Parser evaluation (SPEC §20.4): LLM vs regex on data/parser_eval.jsonl, misses reported honestly.

    python tools/eval_parser.py            # → results/parser_eval.md   (LLM rows need Ollama running)

An event counts as extracted when the deterministic proposal validator accepts it (ready or needs
clarification) with exactly the labelled fields. Unknown trains / platforms must be rejected.
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from railflow import llm  # noqa: E402
from railflow.models import Station, TimetableIn  # noqa: E402
from railflow.parser_llm import call_llm  # noqa: E402
from railflow.parser_regex import parse_regex  # noqa: E402
from railflow.proposals import normalise, validate_proposals  # noqa: E402
from railflow.timeutil import to_min  # noqa: E402


def key(e: dict) -> tuple:
    if e["type"] == "delay":
        return ("delay", e["train_id"], int(e["minutes"]), e.get("kind") or "arrival")
    return ("closure", e["platform_id"], e["start"], e["end"])


def run(path: str, rows: list[dict], station: Station, tt) -> dict:
    ids = [t.id for t in tt.trains]
    tp = fp = fn = exact = rej_ok = rej_n = 0
    wrong = wrong_flagged = 0
    ms: list[float] = []
    by_cat: dict[str, list[int]] = {}
    misses: list[str] = []
    for r in rows:
        norm = normalise(r["text"], ids)
        t0 = time.perf_counter()
        res = call_llm(r["text"], station.platform_ids, ids) if path == "llm" else parse_regex(norm.text)
        ms.append((time.perf_counter() - t0) * 1000)
        if res is None:
            res = {"events": [], "unparsed": [r["text"]]}
        ok, rejected, _ = validate_proposals(res.get("events", []), res.get("unparsed", []), r["text"], station, tt,
                                             to_min(r["now"]))
        got = {key({"type": p.type, "train_id": p.train_id, "minutes": p.minutes, "kind": p.kind,
                    "platform_id": p.platform_id, "start": p.start, "end": p.end}) for p in ok}
        want = {key(e) for e in r["expected"]}
        for prop in ok:                                   # a wrong value must not reach the operator as "ready"
            k = key({"type": prop.type, "train_id": prop.train_id, "minutes": prop.minutes, "kind": prop.kind,
                     "platform_id": prop.platform_id, "start": prop.start, "end": prop.end})
            if k not in want:
                wrong += 1
                wrong_flagged += prop.status != "ok"
        tp += len(got & want); fp += len(got - want); fn += len(want - got)
        hit = got == want
        exact += hit
        by_cat.setdefault(r["category"], [0, 0])[0] += hit
        by_cat[r["category"]][1] += 1
        if r["expect_rejected"]:                         # never guessed: nothing accepted, something rejected
            rej_n += 1
            rej_ok += not ok and bool(rejected)
        if not hit:
            misses.append(f"| {r['id']} | {r['category']} | {r['text']} | {sorted(want)} | {sorted(got)} |")
    n = len(rows)
    return {"precision": tp / (tp + fp) if tp + fp else 1.0, "recall": tp / (tp + fn) if tp + fn else 1.0,
            "exact": exact, "n": n, "rej_ok": rej_ok, "rej_n": rej_n, "median_ms": statistics.median(ms),
            "by_cat": by_cat, "misses": misses, "wrong": wrong, "wrong_flagged": wrong_flagged}


def main() -> None:
    station = Station.model_validate_json((ROOT / "data" / "station_shivneri.json").read_text(encoding="utf-8"))
    tt = TimetableIn.model_validate_json((ROOT / "data" / "timetable_normal.json").read_text(encoding="utf-8")).to_timetable()
    rows = [json.loads(line) for line in (ROOT / "data" / "parser_eval.jsonl").read_text(encoding="utf-8").splitlines() if line]
    paths = ["regex"] + (["llm"] if llm.resolve_model() else [])
    res = {p: run(p, rows, station, tt) for p in paths}
    model = llm.resolve_model() or "unavailable"
    out = ["# Parser evaluation (measured)", "",
           f"{len(rows)} labelled messages from `data/parser_eval.jsonl` (10 Devanagari, 2 radio transcripts). "
           f"LLM: local Ollama `{model}`, temperature 0, 8 s timeout. "
           "An event counts only if the deterministic proposal validator accepts it with exactly the labelled fields.", "",
           "| Path | Event precision | Event recall | Exact-match messages | Correct rejections (unknown IDs) | Wrong values flagged for clarification | Median latency |",
           "|---|---|---|---|---|---|---|"]
    for p, r in res.items():
        out.append(f"| {p} | {r['precision']:.2f} | {r['recall']:.2f} | {r['exact']}/{r['n']} | {r['rej_ok']}/{r['rej_n']} | "
                   f"{r['wrong_flagged']}/{r['wrong']} | {r['median_ms']:.0f} ms |")
    if "llm" not in res:
        out.append("| llm | not run — Ollama unavailable | | | | |")
    cats = sorted({c for r in res.values() for c in r["by_cat"]})
    out += ["", "Exact-match by category:", "", "| Category | " + " | ".join(res) + " |", "|---|" + "---|" * len(res)]
    for c in cats:
        out.append(f"| {c} | " + " | ".join(f"{r['by_cat'].get(c, [0, 0])[0]}/{r['by_cat'].get(c, [0, 0])[1]}" for r in res.values()) + " |")
    for p, r in res.items():
        out += ["", f"## Misses — {p} ({len(r['misses'])})", "", "| Id | Category | Message | Expected | Accepted |", "|---|---|---|---|---|"]
        out += r["misses"] or ["| — | | | | |"]
    path = ROOT / "results" / "parser_eval.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:8 + len(res)]))


if __name__ == "__main__":
    main()
