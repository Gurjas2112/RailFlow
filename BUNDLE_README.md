# RailFlow — design bundle v1.7

Everything the coding agent needs, laid out as it goes into the repo. Copy the folders into `C:\dev\railflow` as they are.

| Path | What it is | Version / check |
|---|---|---|
| `AGENTS.md` | Coding-agent instructions: rules, stack, layout, tests, tiered definition of done, phase prompts | v1.7 |
| `docs/SPEC.md` | Engineering specification (source of truth), Parts I–XIII | v1.7 |
| `docs/JUDGE_AUDIT.md` | Judge review answered claim by claim, with evidence; v1.7 addendum on opposite-direction movements | v1.6 + v1.7 addendum |
| `data/station_shivneri.json` | Shivneri Junction (SVNJ), 5 PFs, lengths in coaches, goods loop in wagons, EN/हिं/मर aliases | IR format, fictional |
| `data/timetable_normal.json` | 30 trains, conflict-free (platforms) | 0 platform conflicts |
| `data/timetable_conflicts.json` | Same trains, 3 planted conflicts | PF 1 short 2 · PF 2 short 3 · PF 4 stays 5 / reserved 10 |
| `data/demo/shivneri_timetable_demo.xlsx` | IR working-timetable workbook: Read me, Station (named cells), two timetables, formula Answer key, Demo script | 104 formulas, 0 errors |
| `data/demo/radio_s2_en.wav` / `.mp3` | Synthetic radio report: 11209 +30, PF 3 closed 14:00–15:30 | 20.7 s, 16 kHz mono |
| `data/demo/radio_s2_hi.wav` / `.mp3` | Same report in Hindi | 17.1 s |
| `data/demo/radio_transcripts.txt` | Exact scripts and expected events | — |
| `tools/reference/rf_reference.py` | Reference model (oracle, never imported by the product) | OR-Tools 9.15 |
| `tools/reference/run_reference.py` | Regenerates `REFERENCE_RUN.md` | Deterministic (seed 42) |
| `tools/reference/REFERENCE_RUN.md` | Expected results for S1, S2, S3, S5, S8 and the hierarchy check | Reproduced twice, byte-identical |
| `tools/reference/route_experiment.py` | Tier 3 throat route-conflict experiment (SPEC §48) | — |
| `tools/reference/ROUTE_EXPERIMENT.md` | 7 route conflicts as scheduled → 0 after solving | Weighted delay 16, OPTIMAL |

**Regenerate the oracle** (only if the shipped data changes):

```bash
pip install ortools
python tools/reference/run_reference.py data > tools/reference/REFERENCE_RUN.md
python tools/reference/route_experiment.py data > tools/reference/ROUTE_EXPERIMENT.md
```

**Not in this bundle:**
- The product code itself; nothing has been implemented or tested yet.
- The Figma file: [RailFlow — UX Flow](https://www.figma.com/design/ReH4Wiyoa7NjtJQQ2VVmu4).

All data is fictional.
