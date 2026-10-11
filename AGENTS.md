# AGENTS.md — RailFlow coding-agent instructions (v1.7, reconstructed)

> **Provenance.** The original v1.7 `AGENTS.md` listed in `BUNDLE_README.md` was not present in the bundle.
> This file was reconstructed from `docs/SPEC.md` v1.7 (§1, §17–§20, §28, §30–§33, §47–§48). Where this file and
> the spec disagree, **the spec wins**.

## 1 · Thesis — never break

**The planner may be wrong; the validator cannot be fooled; the AI never touches a platform.**

- One occupancy definition everywhere: a train on platform *p* occupies `[arr, dep + min_gap)`; a closure occupies `[start, end)`.
- V8 conflicts always report `stay_overlap_min`, `clearance_shortfall_min` and `reserved_overlap_min` (§47.1).
- Arrival and departure delays are accounted separately; expected stay = original dwell + cumulative **departure** delay (§47.2).
- Lexicographic objective: Σπ·unassigned, then the primary goal, then the secondary goal (§47.5).
- The VALID badge comes only from `validator.py`; the Recovery badge (FULLY ASSIGNED / PARTIAL / SOLVER FAILED) is separate (§47.6).
- `validator.py` imports only `.models` and the standard library, checks with a sweep line and reports every violating pair (§9, §20.2).
- The AI outputs only `Disruption[]` proposals or explanation text. An operator confirms every proposal before planning (§4, §5).
- What is applied is exactly what was validated: hash check, re-validation and one transaction (§31).

## 2 · Rules for the agent

1. `docs/SPEC.md` is the source of truth. Do not add features that are not in it.
2. Never regenerate or edit the shipped data: `data/station_shivneri.json`, `data/timetable_normal.json`, `data/timetable_conflicts.json`, `data/demo/*`.
3. `tools/reference/` is an oracle. Product code never imports it; `test_reference_parity.py` compares against its numbers.
4. Phase N+1 does not start until phase N's tests are green. Tier 3 starts only after Tier 1 and Tier 2 are green.
5. Every visible UI string goes through `t('key')`. IDs, times and minutes are never translated.
6. Use `pathlib` everywhere: the repo path may contain spaces (OneDrive).
7. Never commit `.env` or `data/railflow.db*`. Commit only when asked; push only with explicit approval.

## 3 · Stack (fixed — no substitutes)

Python 3.12, FastAPI, Pydantic v2, OR-Tools CP-SAT, argon2-cffi, sqlite3, pytest, Hypothesis ·
React 19, Vite, TypeScript strict, Tailwind v4, zustand, i18next, three / @react-three/fiber / drei, Recharts ·
local Ollama (`qwen2.5:3b`, `qwen2.5:3b-instruct` accepted) · optional faster-whisper `small`.
No Docker, Postgres, ORM, CDN or cloud LLM.

## 4 · Layout

```text
backend/railflow/   main.py · admin.py · models.py · timeutil.py · state.py · planner_cpsat.py · planner_greedy.py
                    validator.py · fault.py · reasons.py · metrics.py · parser_llm.py · parser_regex.py · proposals.py
                    explainer.py · llm.py · audit.py · schema.sql · db.py · auth.py · security.py · events.py
                    timetable_import.py · stt.py · manage.py · config.py · scenario_store.py
backend/tests/      one file per SPEC §20 area (see §8 below)
data/               shipped station + timetables + demo assets; generated timetable_peak.json, scenarios.json, parser_eval.jsonl
tools/              make_data.py · gen_scenarios.py · bench.py · eval_parser.py · check_radio.py · reference/ (oracle)
results/            bench.md · parser_eval.md (committed, measured)
web/src/            api/ (client + generated schema.d.ts) · design/tokens.css · i18n/ · store/sim.ts · sim/ · gantt/
                    panels/ · auth/ · admin/ · layout/
web/public/         locales/{en,hi,mr}.json · fonts/ (local .woff for 3D labels)
```

## 5 · Routes (SPEC §17)

| Route | Role |
|---|---|
| `GET /api/health` · `/api/auth/*` | public |
| `GET /api/scenarios` · `/api/scenario` · `/api/revisions/{id}` · `/api/audit` | viewer, controller, admin (read only) |
| `POST /api/scenario/load` · `/reset` · `/validate/scheduled` · `/assign` · `/disruptions/parse` · `/disruptions/transcribe` · `/plan` · `/explain` · `/revisions/{id}/apply` · `/timetable/upload` | controller |
| `/api/admin/*` · `GET /api/audit/verify` | admin |

Admin cannot parse, plan or apply. Every refusal returns 403 and writes a `refused` audit entry and event.

## 6 · Phases and gates

| Phase | Scope | Gate |
|---|---|---|
| 0 | Scaffold, models, schema, routes, Vite + i18n shell | backend starts; shell at 360 px and 1366 px; `git check-ignore .env` |
| 1 | planner, validator, state, db, import, generated data, Gantt | Phase 1 tests + reference parity green; workbook shows its 3 conflicts |
| 2 | parse, plan, explain, apply; Disruption, Compare, Changes, ReasonCard | S2 @ 13:50 end to end; S2-late and S4 rejected; S8 trade-off; S5 NOT VALID with Apply disabled; Ollama down → regex/template |
| 3 | auth, roles, admin dashboard (Tier 3) | viewer → Apply 403; admin → Plan 403; both visible in audit and dashboard |
| 4 | 3D + TopView2D, phone/tablet/desktop, hi/mr (Tier 3) | Vitest green; before/after; EN · हिं · मर on every screen |
| 5 | STT, single-process demo, bench, parser eval, README | evidence committed; definition of done marked |

## 7 · Commands

```powershell
cd backend; python -m pytest -q                         # all backend tests
cd web; npm test; npm run build                         # Vitest + typecheck + build
python tools/make_data.py                               # regenerate derived data (seed 42), asserts JSON twins = workbook
python tools/bench.py; python tools/eval_parser.py      # → results/
npm run gen:api                                         # web/src/api/schema.d.ts from a running backend
```

## 8 · Tests (SPEC §20)

`test_validator` · `test_validator_independence` · `test_planner_properties` (Hypothesis, 200 examples ×2) ·
`test_delay_accounting` · `test_objective_and_capacity` (hierarchy, wagons, recovery) · `test_reference_parity` ·
`test_timetable_import` · `test_parser` · `test_explainer_grounding` · `test_api` · `test_departure_delay` ·
`test_affected_set` · `test_cascade` · `test_auth` · `test_storage_integrity` · `test_locales` · `test_stt` ·
web: `locales.test.ts` · `pose.test.ts`.

## 9 · Definition of done — status at hand-over (2026-10-11)

**Tier 1 — core (P-03 graded requirements)**

- [x] Conflict-free assignment with minimum gap and required platforms (S1, `/api/assign`) — PASS
- [x] Conflicts reported by train and platform with minutes; workbook Answer key reproduced (S3) — PASS
- [x] Replanning after delays and closures, only the affected set moves, reasons recorded (S2, S8) — PASS
- [x] Independent validator V1–V10, sweep line, import test, fault injection caught (S5) — PASS
- [x] Reference parity: S1, S2, S3, S5, S8 and the lexicographic check — PASS
- [x] Property tests: 200 random cases, every revision valid, every injected fault caught — PASS

**Tier 2 — AI and apply**

- [x] Parser LLM + regex fallback, proposal validator (unknown IDs rejected, never guessed), human confirmation — PASS
- [x] Explainer with number-grounding check and template fallback; hi/mr always template — PASS
- [x] Apply = hash check + re-validation + one transaction; 409 on invalid / fault / mismatch / stale — PASS
- [x] Ollama down → `regex` / `template` chips (covered by tests with Ollama unreachable) — PASS

**Tier 3 — platform, reach, assets**

- [x] Auth: Argon2id, sessions 30 min idle / 8 h absolute, lockout, invites, role guards, CSP, Origin check — PASS
- [x] Admin dashboard, six panels, 5 s poll, alert tiles — PASS
- [x] 3D station and 2D top view from `trainPose()`; Gantt truth view — PASS (headless Edge, SwiftShader)
- [x] Phone / tablet / desktop layouts; no horizontal page scroll at 360 px and 768 px — PASS (emulated)
- [x] EN · हिं · मर locales complete — PASS (machine-checked; **native-speaker review still required**, §37)
- [x] Single-process demo mode, `start.ps1` / `start.sh` — PASS
- [x] Benchmark and parser evaluation committed with measured numbers — PASS
- [~] Speech-to-text — BUILT and tested with a mocked model; `faster-whisper` is not installed on the build machine, so `tools/check_radio.py` has not been run against the real clips
- [ ] Route conflicts V11 (§48) — NOT BUILT (roadmap; limitation stated in README)
- [ ] Real-phone-on-hotspot check, offline (Wi-Fi off) dry run, backup video — NOT DONE (needs the demo laptop and people)
