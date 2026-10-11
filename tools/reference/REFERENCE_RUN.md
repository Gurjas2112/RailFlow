# Reference run (generated)

Produced by `reference/run_reference.py` on the shipped data. Every number below is computed, not typed. Deterministic: seed 42, no timings (measure speed with bench.py on the laptop).

## S3 — timetable as scheduled

| Rule | PF | Trains | Stay overlap | Clearance shortfall | Reserved overlap |
|---|---|---|---|---|---|
| GAP_VIOLATION | P1 | 11214 ↔ 11216 | 0 | 2 | 2 |
| GAP_VIOLATION | P2 | 51218 ↔ 51219 | 0 | 3 | 3 |
| OVERLAP | P4 | 51214 ↔ 51215 | 5 | — | 10 |

Conflict-free sheet: 0 conflicts.

## S1 — assign platforms (now 00:00)

All trains movable; scheduled platforms as the base.

Affected set (cascade-closed):  — 0 of 30.

| Revision | Validator | Recovery | Platform changes | Total hold (min) | Weighted delay | Solver |
|---|---|---|---|---|---|---|
| CP-SAT min_delay | VALID | FULLY_ASSIGNED | 0 | 0 | 0 | OPTIMAL |
| CP-SAT min_changes | VALID | FULLY_ASSIGNED | 0 | 0 | 0 | OPTIMAL |
| Greedy (stage 1) | VALID | FULLY_ASSIGNED | 0 | 0 | 0 | HEURISTIC |

**min_delay** changes:


**min_changes** changes:


**greedy** changes:


## S2 — 11209 +30 min, PF 3 closed 14:00–15:30 (now 13:50)

At 14:05 the same message must be rejected: 11209 has arrived at 14:02.

Affected set (cascade-closed): 11209, 11217, 51219 — 3 of 30.

| Revision | Validator | Recovery | Platform changes | Total hold (min) | Weighted delay | Solver |
|---|---|---|---|---|---|---|
| CP-SAT min_delay | VALID | FULLY_ASSIGNED | 3 | 16 | 45 | OPTIMAL |
| CP-SAT min_changes | VALID | FULLY_ASSIGNED | 3 | 16 | 45 | OPTIMAL |
| Greedy (stage 1) | VALID | FULLY_ASSIGNED | 3 | 16 | 45 | HEURISTIC |

**min_delay** changes:

- 11209: P3 14:02 → P4 14:45 (hold 13)
- 51219: P3 14:22 → P2 14:25 (hold 3)
- 11217: P3 14:50 → P1 14:50 (hold 0)

**min_changes** changes:

- 11209: P3 14:02 → P4 14:45 (hold 13)
- 51219: P3 14:22 → P2 14:25 (hold 3)
- 11217: P3 14:50 → P1 14:50 (hold 0)

**greedy** changes:

- 51219: P3 14:22 → P2 14:25 (hold 3)
- 11209: P3 14:02 → P4 14:45 (hold 13)
- 11217: P3 14:50 → P1 14:50 (hold 0)

## S8 — 51218 departure +25, PF 3 closed 14:30–15:10 (now 14:10)



Affected set (cascade-closed): 11217, 51215, 51218, 51219 — 4 of 30.

| Revision | Validator | Recovery | Platform changes | Total hold (min) | Weighted delay | Solver |
|---|---|---|---|---|---|---|
| CP-SAT min_delay | VALID | FULLY_ASSIGNED | 2 | 38 | 76 | OPTIMAL |
| CP-SAT min_changes | VALID | FULLY_ASSIGNED | 1 | 58 | 136 | OPTIMAL |
| Greedy (stage 1) | VALID | FULLY_ASSIGNED | 3 | 40 | 85 | HEURISTIC |

**min_delay** changes:

- 51218: P2 14:00 → P2 14:00 (hold 0)
- 51219: P3 14:22 → P4 14:45 (hold 23)
- 51215: P2 14:35 → P2 14:50 (hold 15)
- 11217: P3 14:50 → P1 14:50 (hold 0)

**min_changes** changes:

- 51218: P2 14:00 → P2 14:00 (hold 0)
- 51219: P3 14:22 → P4 14:45 (hold 23)
- 51215: P2 14:35 → P2 14:50 (hold 15)
- 11217: P3 14:50 → P3 15:10 (hold 20)

**greedy** changes:

- 51218: P2 14:00 → P2 14:00 (hold 0)
- 51219: P3 14:22 → P4 14:45 (hold 23)
- 51215: P2 14:35 → P1 14:47 (hold 12)
- 11217: P3 14:50 → P4 14:55 (hold 5)

## S5 — fault injection on S8 min_delay

- OVERLAP · P1 · 12222 ↔ 51215 · {'stay_overlap_min': 7, 'clearance_shortfall_min': None, 'reserved_overlap_min': 12}

## Lexicographic check — PF 4 (only goods PF) closed 12:30–13:00

Unassigned: [] · held: [('GDS-4105', 20)] · stages: [('OPTIMAL', 0), ('OPTIMAL', 20), ('OPTIMAL', 0)]

