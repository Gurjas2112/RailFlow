# RailFlow — Judge audit and reconciliation (v1.6, updated for v1.7)

**Scope.** This audit answers the external judge review against the actual files: `SPEC.md` v1.5, `AGENTS.md`, the station and timetable JSON, `shivneri_timetable_demo.xlsx` and the radio transcripts. Every expected result below was produced by `reference/run_reference.py`, a small reference model of the v1.6 semantics running OR-Tools CP-SAT 9.15. Its full output is in `reference/REFERENCE_RUN.md`.

**What this audit does not claim.** The RailFlow product itself (FastAPI, React, tests) has **not** been implemented or run. The reference model is an oracle for the product's tests, not the product.

## 1. Verdict

**Go for the core build, after the v1.6 fixes below (all applied).**
- Design and data: consistent after the fixes.
- Implementation: unverified until the product's tests run.
- Scope: Tier 1 is the mandatory MVP; everything else is gated (AGENTS.md §9).

## 2. Review findings — verified against the files

| # | Review claim | Verified? | Evidence | Fix in v1.6 |
|---|---|---|---|---|
| P0-1 | Conflict classification imprecise: "OVERLAP 10 min" for 51214/51215 is the reserved-interval figure, not the actual stay overlap | ✅ **Correct** | Stays overlap 5 min; `[arr, dep+gap)` intervals overlap 10 min. The other two pairs are pure clearance shortfalls of 2 and 3 min. | Every conflict carries `stay_overlap_min`, `clearance_shortfall_min` and `reserved_overlap_min`. Codes unchanged. Workbook answer key computes all three by formula. UI labels both. (SPEC §47.1) |
| P0-2 | The validator code sums all delay kinds into one total | ✅ **Correct** | §9 code used one `delay[...] += minutes`, inconsistent with v1.4's V4 and V5 rules | Separate `arr_delay` and `dep_delay` in the validator, planner, greedy, state and reasons; six new tests. (SPEC §47.2) |
| P0-3 | Goods 58 "coaches" on a 24-coach PF | ✅ **Correct** | JSON had `coaches: 58` for GDS-4105 and GDS-4237 on P4 (`length_coaches` 24) | Goods use `wagons`, PF 4 has `goods_loop_wagons: 60`, and units are never mixed. New validator rule **V10 `CAPACITY_EXCEEDED`** checks capacity itself rather than trusting the allowed list. (SPEC §47.3) |
| P0-4 | Workbook cells vs documents disagree | ✅ **Correct** | Workbook: code B3, clearance **B4**, hold **B5**. SPEC §40 said B3/B4. | Workbook defines names **`MinClearance`** and **`MaxHold`**; all formulas and the importer use names or labels, never coordinates. (SPEC §47.4) |
| P0-5 | Weighted objective does not guarantee "unassigned costs most" | ✅ **Correct** | 100 000 per unassigned train vs up to 45 min × 4 × 100 per held train: at 200 trains, delays can outweigh one unassignment | **Sequential lexicographic solve:** minimise Σπ·unassigned, freeze it, then the primary objective, freeze it, then the secondary. Reference check: closing the only goods PF holds GDS-4105 by 20 min instead of unassigning it. (SPEC §47.5) |
| P1-6 | "Valid" may hide unassigned trains | ✅ **Correct** | A valid revision could contain UNASSIGNED trains under a green badge | Two badges: **Validator** VALID / NOT VALID, and **Recovery** FULLY_ASSIGNED / PARTIAL / SOLVER_FAILED. A timeout is never reported as infeasible. (SPEC §47.6) |
| Scope | Too much for 12 hours | ✅ **Agreed** | — | AGENTS.md §9 split into Tier 1 (mandatory), Tier 2 (high value) and Tier 3 (gated). Phases 3–5 extras are optional behind cut gates. |

## 3. Additional defects found by running the reference model

| # | Finding | Evidence | Fix |
|---|---|---|---|
| A-1 | **S2 is impossible at 14:05**, the time on the demo screens | 11209 arrives at 14:02, so at 14:05 it is at PF 3 and an arrival delay must be rejected (SPEC §6, §43) | S2 runs at **now = 13:50**. Spec, workbook, scenarios and Figma updated. The 14:05 rejection is kept as a deliberate negative test. |
| A-2 | **Trade-off numbers for S2 were illustrative and wrong** | Real solve: min-delay, min-changes and greedy all give 3 moves, 16 min total hold, weighted delay 45. The PF 3 closure forces 11209, 51219 and 11217 to move. | Spec and Figma show the real numbers. The compare panel says "all revisions agree" when they do. The trade-off demo moves to **S8**. |
| A-3 | **S8 expected table was the greedy result, not CP-SAT** | CP-SAT min-delay: 2 moves, hold 38, weighted 76. Min-changes: 1 move, hold 58, weighted 136. Greedy: 3 moves, weighted 85. | SPEC §45 table replaced with the CP-SAT results. Greedy is shown as the baseline it is. |
| A-4 | **S2 reason card was wrong** | 11209 goes to PF 4 at 14:45 (held 13, behind 51214), not PF 2 | Figma flow 5 and the spec example reason updated. |

## 4. Verified results (from `REFERENCE_RUN.md`)

| Scenario | Affected | Validator | Recovery | Key numbers |
|---|---|---|---|---|
| S3 as scheduled | — | 3 conflicts | — | PF 1 short 2 · PF 2 short 3 · PF 4 stays 5 / reserved 10 |
| Conflict-free sheet | — | 0 conflicts | — | — |
| S1 assign | 0 of 30 | VALID | FULLY_ASSIGNED | 0 changes, 0 hold, OPTIMAL |
| S2 @ 13:50 | 3 of 30 | VALID | FULLY_ASSIGNED | All methods: 3 changes, 16 min, weighted 45 |
| S8 @ 14:10 | 4 of 30 | VALID | FULLY_ASSIGNED | A 2 changes / 76 · B 1 change / 136 · greedy 3 / 85 |
| S5 fault (on S8) | — | **NOT VALID** | — | OVERLAP PF 1 12222 ↔ 51215, stays 7 / reserved 12 |
| Lexicographic check | — | VALID | FULLY_ASSIGNED | GDS-4105 held 20, 0 unassigned |

Solve times were all under 0.05 s on the sandbox CPU; measure again on the team laptop.

## 5. Still unverified (needs the product)

- The product's validator, planner and importer pass the same results as the reference (`test_reference_parity.py`).
- Parser accuracy (LLM vs regex), and speech-to-text on the radio clips (`check_radio.py` on the laptop).
- UI behaviour, layouts, languages, offline run, auth and the dashboard.
- Benchmark numbers on the laptop (`bench.py`).

## 6. Related work, stated honestly

Liu, Zhou, Dong, Wu, Li & Wang (2023), *ADMM-based joint rescheduling method for high-speed railway timetabling and platforming in case of uncertain perturbation*, Transportation Research Part C 152:104150. It treats retiming and re-platforming as one coupled problem, which supports RailFlow's joint hold-and-platform decision. RailFlow does **not** implement the paper's MILP, ADMM decomposition, MPC horizon or chance constraints. It is a single-station CP-SAT model with an independent validator, and should be pitched that way.

## 7. v1.7 addendum — opposite-direction movements

Asked: should two trains coming from opposite directions simply get more delay?

**Answer:** no. On a platform, direction does not matter, and v1.6 already checks platform occupancy regardless of direction. In the station throat, crossing routes need their own no-overlap constraints in the same CP-SAT model. The solver then re-platforms or holds, and precedence decides who waits.

**Experiment** (`reference/route_experiment.py` → `ROUTE_EXPERIMENT.md`):
- the conflict-free timetable contains **7 throat route conflicts**;
- CP-SAT with route constraints resolves all 7 (weighted delay 16, 4 platform changes, OPTIMAL);
- the Superfast 12222 is re-platformed, not held;
- the result has 0 platform conflicts under the reference validator.

**Status:** SPEC §48, Tier 3, behind the flag `model_routes` (default off). Tier 1 results and reference parity are unaffected. Limitation stated: route conflicts are not modelled in the MVP; single-line crossings between stations are out of scope.
