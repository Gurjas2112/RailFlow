# Benchmark (measured)

`python tools/bench.py --seed 7 --n 20` on `data/timetable_peak.json` (36 trains): 1–3 delays of 5–45 min and 0–2 closures of 30–120 min per scenario, applied plan = scheduled platforms. Machine: Intel64 Family 6 Model 141 Stepping 1, GenuineIntel · Python 3.12.0. Solve time includes the two-stage affected-set solve and, when needed, the widened stage.

| Method | Valid plans | Total weighted delay (sum) | Platform changes (sum) | Unassigned (sum) | Median solve time | OPTIMAL proven | Widened |
|---|---|---|---|---|---|---|---|
| Greedy | 20/20 | 1847 | 92 | 5 | 0 ms | — | 10/20 |
| CP-SAT min-delay | 20/20 | 1526 | 91 | 4 | 66 ms | 20/20 | 10/20 |
| CP-SAT min-changes | 20/20 | 4008 | 25 | 4 | 66 ms | 20/20 | 10/20 |

Per scenario:

| Scenario | Method | Valid | Weighted delay | Changes | Unassigned | Status |
|---|---|---|---|---|---|---|
| B01 | CP-SAT min-changes | VALID | 126 | 1 | 0 | OPTIMAL |
| B01 | CP-SAT min-delay | VALID | 126 | 1 | 0 | OPTIMAL |
| B01 | Greedy | VALID | 126 | 1 | 0 | HEURISTIC |
| B02 | CP-SAT min-changes | VALID | 162 | 0 | 0 | OPTIMAL |
| B02 | CP-SAT min-delay | VALID | 129 | 1 | 0 | OPTIMAL |
| B02 | Greedy | VALID | 129 | 1 | 0 | HEURISTIC |
| B03 | CP-SAT min-changes | VALID | 246 | 5 | 0 | OPTIMAL |
| B03 | CP-SAT min-delay | VALID | 57 | 12 | 0 | OPTIMAL |
| B03 | Greedy | VALID | 127 | 8 | 0 | HEURISTIC |
| B04 | CP-SAT min-changes | VALID | 589 | 2 | 1 | OPTIMAL |
| B04 | CP-SAT min-delay | VALID | 188 | 6 | 1 | OPTIMAL |
| B04 | Greedy | VALID | 190 | 10 | 1 | HEURISTIC |
| B05 | CP-SAT min-changes | VALID | 32 | 0 | 0 | OPTIMAL |
| B05 | CP-SAT min-delay | VALID | 0 | 1 | 0 | OPTIMAL |
| B05 | Greedy | VALID | 0 | 1 | 0 | HEURISTIC |
| B06 | CP-SAT min-changes | VALID | 0 | 0 | 0 | OPTIMAL |
| B06 | CP-SAT min-delay | VALID | 0 | 0 | 0 | OPTIMAL |
| B06 | Greedy | VALID | 0 | 0 | 0 | HEURISTIC |
| B07 | CP-SAT min-changes | VALID | 97 | 2 | 0 | OPTIMAL |
| B07 | CP-SAT min-delay | VALID | 57 | 7 | 0 | OPTIMAL |
| B07 | Greedy | VALID | 97 | 9 | 0 | HEURISTIC |
| B08 | CP-SAT min-changes | VALID | 0 | 0 | 0 | OPTIMAL |
| B08 | CP-SAT min-delay | VALID | 0 | 0 | 0 | OPTIMAL |
| B08 | Greedy | VALID | 0 | 0 | 0 | HEURISTIC |
| B09 | CP-SAT min-changes | VALID | 60 | 0 | 0 | OPTIMAL |
| B09 | CP-SAT min-delay | VALID | 0 | 1 | 0 | OPTIMAL |
| B09 | Greedy | VALID | 0 | 1 | 0 | HEURISTIC |
| B10 | CP-SAT min-changes | VALID | 197 | 1 | 0 | OPTIMAL |
| B10 | CP-SAT min-delay | VALID | 18 | 8 | 0 | OPTIMAL |
| B10 | Greedy | VALID | 55 | 7 | 0 | HEURISTIC |
| B11 | CP-SAT min-changes | VALID | 18 | 0 | 0 | OPTIMAL |
| B11 | CP-SAT min-delay | VALID | 0 | 1 | 0 | OPTIMAL |
| B11 | Greedy | VALID | 0 | 1 | 0 | HEURISTIC |
| B12 | CP-SAT min-changes | VALID | 433 | 3 | 0 | OPTIMAL |
| B12 | CP-SAT min-delay | VALID | 363 | 4 | 0 | OPTIMAL |
| B12 | Greedy | VALID | 363 | 4 | 0 | HEURISTIC |
| B13 | CP-SAT min-changes | VALID | 89 | 2 | 1 | OPTIMAL |
| B13 | CP-SAT min-delay | VALID | 68 | 5 | 1 | OPTIMAL |
| B13 | Greedy | VALID | 102 | 6 | 1 | HEURISTIC |
| B14 | CP-SAT min-changes | VALID | 217 | 1 | 0 | OPTIMAL |
| B14 | CP-SAT min-delay | VALID | 61 | 6 | 0 | OPTIMAL |
| B14 | Greedy | VALID | 138 | 3 | 0 | HEURISTIC |
| B15 | CP-SAT min-changes | VALID | 6 | 0 | 0 | OPTIMAL |
| B15 | CP-SAT min-delay | VALID | 6 | 0 | 0 | OPTIMAL |
| B15 | Greedy | VALID | 6 | 0 | 0 | HEURISTIC |
| B16 | CP-SAT min-changes | VALID | 86 | 2 | 0 | OPTIMAL |
| B16 | CP-SAT min-delay | VALID | 41 | 4 | 0 | OPTIMAL |
| B16 | Greedy | VALID | 41 | 4 | 0 | HEURISTIC |
| B17 | CP-SAT min-changes | VALID | 267 | 1 | 1 | OPTIMAL |
| B17 | CP-SAT min-delay | VALID | 50 | 7 | 1 | OPTIMAL |
| B17 | Greedy | VALID | 50 | 10 | 1 | HEURISTIC |
| B18 | CP-SAT min-changes | VALID | 566 | 0 | 0 | OPTIMAL |
| B18 | CP-SAT min-delay | VALID | 94 | 9 | 0 | OPTIMAL |
| B18 | Greedy | VALID | 151 | 11 | 0 | HEURISTIC |
| B19 | CP-SAT min-changes | VALID | 432 | 2 | 1 | OPTIMAL |
| B19 | CP-SAT min-delay | VALID | 138 | 9 | 1 | OPTIMAL |
| B19 | Greedy | VALID | 162 | 5 | 1 | HEURISTIC |
| B20 | CP-SAT min-changes | VALID | 385 | 3 | 0 | OPTIMAL |
| B20 | CP-SAT min-delay | VALID | 130 | 9 | 0 | OPTIMAL |
| B20 | Greedy | VALID | 110 | 10 | 1 | HEURISTIC |
