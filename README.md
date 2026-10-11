# RailFlow

**Railway disruption & platform conflict simulator** — an auditable, AI-assisted disruption decision-support
simulator with independently verified scheduling outcomes. VORTEXA 3.0 · P-03. All data is fictional
(Shivneri Junction, SVNJ). Advisory only: not a safety system and not connected to signalling.

> The planner may be wrong; the validator cannot be fooled; the AI never touches a platform.

- **Planner:** OR-Tools CP-SAT (sequential lexicographic objective, two-stage affected-set replanning) plus a greedy baseline.
- **Validator:** `backend/railflow/validator.py`, written independently. It imports only `.models` and the standard library, checks with a sweep line, and decides every VALID badge.
- **AI:** a local Ollama model turns operator text into *proposed* delays and closures, which a controller confirms, and explains trade-offs in sentences whose every number is checked. The AI outputs cannot express a platform assignment.
- **Audit:** every confirmation, plan, apply and refusal is recorded in a SHA-256 hash chain. What is applied is exactly the revision that was validated.

Full engineering specification: [`docs/SPEC.md`](docs/SPEC.md). Agent instructions and definition of done: [`AGENTS.md`](AGENTS.md).

## Repository map

| Folder | What is in it |
|---|---|
| [`backend/railflow/`](backend/railflow/) | FastAPI app: planner (CP-SAT + greedy), independent validator, AI parser/explainer, auth, audit, storage |
| [`backend/tests/`](backend/tests/) | pytest suite, one file per SPEC §20 area |
| [`web/`](web/) | React 19 + Vite UI: Gantt, 3D/2D station, disruption and compare panels, admin dashboard, EN/हिं/मर |
| [`data/`](data/) | Fictional Shivneri Junction station, timetables, scenarios, demo workbook and radio clips |
| [`tools/`](tools/) | Data generation, benchmark, parser evaluation; `tools/reference/` is the independent oracle |
| [`results/`](results/) | Measured benchmark and parser-evaluation reports |
| [`docs/`](docs/) | Engineering spec, judge audit, hackathon report (DOCX + PDF) |
| [`app_screenshots_&_screen_recordings/`](app_screenshots_&_screen_recordings/) | Flow-by-flow screenshots and the full demo recording |

## Setup (once)

Requirements: Python 3.12, Node 20.19+ (or 22.12+), and optionally [Ollama](https://ollama.com) with `qwen2.5:3b` (or `qwen2.5:3b-instruct`).

```powershell
copy .env.example .env            # then set the three demo passwords (≥ 12 characters each)
cd backend
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..\web; npm install
ollama pull qwen2.5:3b            # optional: without it, the regex parser and template explainer are used
```

## The four commands

```powershell
# 1 · database and demo accounts (idempotent; passwords read from .env)
cd backend; python -m railflow.manage init-db; python -m railflow.manage seed-demo

# 2 · development: API on :8000 (localhost only) + web on :5173 with /api proxied
uvicorn railflow.main:app --host 127.0.0.1 --port 8000 --reload
cd web; npm run dev

# 3 · demo day: one process, one port, works offline (-Lan to let phones on the hotspot connect)
.\start.ps1            # or ./start.sh on macOS/Linux

# 4 · tests and evidence
cd backend; python -m pytest -q
cd web; npm test
python tools/bench.py; python tools/eval_parser.py      # → results/bench.md, results/parser_eval.md
```

Other management commands: `python -m railflow.manage create-admin <name>` (prompts for a password), `unlock <user>`, `backup`.
Regenerate derived data with `python tools/make_data.py` (seed 42; it also asserts that the JSON twins equal the workbook import).

## Demo accounts

`seed-demo` creates **viewer**, **controller** and **admin** with the passwords you set in `.env`
(`RAILFLOW_VIEWER_PASSWORD`, `RAILFLOW_CONTROLLER_PASSWORD`, `RAILFLOW_ADMIN_PASSWORD`). No default credentials exist in code,
and there is no public sign-up: further accounts come from an admin's single-use, 24-hour invite link.

| Role | Can | Cannot |
|---|---|---|
| viewer | See the station, Gantt, 3D, revisions, reasons, audit list | Parse, plan, apply, load or reset, open `/admin` |
| controller | Everything a viewer can, plus load/reset, check, assign, parse, confirm, plan, explain, apply | Manage users, verify the audit chain, open `/admin` |
| admin | Invite users, change roles, disable users, dashboard, verify the audit chain, read the station | **Parse, plan or apply** (separation of duties) |

Every role check runs on the server; the UI only hides controls. Every refusal is a 403 with a `refused` audit entry.

## Occupancy — the one definition everyone shares

A train assigned to platform *p* occupies **`[arr, dep + min_gap)`**. Two trains on *p* are compatible iff their intervals
do not intersect. A closure **`[start, end)`** on *p* is compatible with a train iff the train's interval does not intersect it.
So a train must leave a closing platform `min_gap` minutes before the closure starts, and may arrive the minute it ends.
Arrival and departure delays are accounted separately: expected arrival = timetable arrival + arrival delay + hold;
expected stay = dwell + departure delay.

## Validator rules

| Rule | Code | Check |
|---|---|---|
| V1 | `MISSING_TRAIN` / `DUPLICATE_TRAIN` / `UNKNOWN_TRAIN` | every timetable train appears exactly once |
| V2 | `UNKNOWN_PLATFORM` | the platform exists |
| V3 | `REQUIRED_PLATFORM` / `NOT_ALLOWED_PLATFORM` | required platform honoured; platform in the allowed list |
| V4 | `DWELL_CHANGED` / `BAD_TIMES` | `dep − arr` = dwell + departure delay; `dep > arr` |
| V5 | `EARLIER_THAN_POSSIBLE` | `arr ≥ timetable arr + arrival delay` |
| V6 | `HOLD_EXCEEDED` | hold ≤ `max_hold` |
| V7 | `FROZEN_CHANGED` | departed / at-platform trains keep platform and arrival |
| V8 | `GAP_VIOLATION` / `OVERLAP` | every pair on a platform keeps the gap; reports stay, clearance and reserved overlap |
| V9 | `CLOSURE_VIOLATION` | no occupancy intersects a closure |
| V10 | `CAPACITY_EXCEEDED` | coaches ≤ platform length; goods wagons ≤ goods-loop wagons |
| — | `UNASSIGNED_WITHOUT_REASON` | an unassigned train carries a reason |

A revision is **valid iff it has zero conflicts**. Validity is not recovery: a valid plan may still be **PARTIAL**.

## Scenarios

| | Scenario | Expected (measured, matches `tools/reference/REFERENCE_RUN.md`) |
|---|---|---|
| S1 | Normal day, assign | VALID, fully assigned, 0 changes |
| S2 | 13:50 · "11209 running 30 min late, platform 3 shut 14:00 to 15:30" | affected 11209, 51219, 11217 · 3 moves · hold 16 · weighted 45 · all revisions agree |
| S2-late | same message at 14:05 | arrival delay rejected: 11209 is already at PF 3 |
| S3 | workbook "Timetable as scheduled" | GAP P1 11214↔11216 (2) · GAP P2 51218↔51219 (3) · OVERLAP P4 51214↔51215 (stay 5, reserved 10) |
| S4 | "11299 delayed 20 min" | rejected, never guessed |
| S5 | S8 + planner fault | A: OVERLAP P1 12222↔51215 (stay 7, reserved 12) → NOT VALID, Apply disabled |
| S6 | peak timetable, PF 2 and PF 4 closed 15:00–16:30 | GDS-4241 UNASSIGNED with its reason; plan still VALID (PARTIAL) |
| S7 | Ollama stopped | parser `regex`, explainer `template`, same plans |
| S8 | 14:10 · 51218 departure +25 · PF 3 closed 14:30–15:10 | affected 4 of 30 · A 2 moves / weighted 76 · B 1 move / weighted 136 · chain 51218 → 51215 |

## Use your own station and timetable

The scenarios are examples; nothing in the planner, validator or parser is tied to them. As a controller, use
**Upload timetable** with either template (links under the upload box, generated by `python tools/make_template.py`):

- **Excel** — [`railflow_template.xlsx`](web/public/templates/railflow_template.xlsx): a *Station* sheet (name, code,
  minimum clearance, maximum hold, then one row per platform: PF · Length (coaches) · Goods loop (wagons) · Use · optional names)
  and a *Timetable* sheet with the working-timetable headers. Up to 20 platforms and 500 trains.
- **JSON** — [`railflow_template.json`](web/public/templates/railflow_template.json): `{"station": {...}, "timetable": {"trains": [...]}}`.
- **CSV** or a workbook without a *Station* sheet: the timetable is checked against the station already loaded.

Platforms get the standard names automatically (`PF 3`, `platform 3`, `प्लेटफॉर्म 3`, `फलाट 3`, …), so typed disruptions
resolve on any station. Every row is checked before anything loads; errors name the sheet, row and column. The template
station (Sahyadri Road, 3 platforms, 8 trains) carries two planted conflicts so a first upload shows detection and replanning.

**Or type it in by hand** — *Enter station and trains by hand* (under the upload box): start from the loaded timetable or
from blank, edit the station (name, code, minimum gap, maximum hold), add or remove platforms and trains, then **Load**.
It goes through the same `POST /api/scenario/load` as an upload, so the server validates every field; obvious slips
(times not HH:MM, departure before arrival, a bad train number) are flagged per row before sending. **Download as JSON**
saves the hand-built station for re-upload. Disruptions can also be entered by hand with **+ delay** / **+ closure**.

When a loaded timetable starts before the current *now*, the clock moves to 30 min before its first arrival, so no train
loads already arrived (and therefore frozen).

## Evidence

- `pytest`: 136 backend tests, including 200 + 200 Hypothesis cases (every revision validates; every injected fault is caught) and reference parity. `npm test`: locale completeness and `trainPose`.
- [`results/bench.md`](results/bench.md), 20 seeded scenarios on the 36-train peak timetable: all methods 20/20 valid. CP-SAT min-delay gives weighted delay 1526 vs greedy 1847; CP-SAT min-changes gives 25 platform changes vs greedy 92. 20/20 OPTIMAL.
- [`results/parser_eval.md`](results/parser_eval.md), 52 labelled messages: LLM 44/52 exact vs regex 36/52 (paraphrases 8/8 vs 3/8, Devanagari 5/10 vs 1/10). Every wrong LLM value (9/9) was caught by the deterministic check and shown as *needs clarification* rather than *ready*.

## Limitations (SPEC §24)

- Single station; **route conflicts in the station throat are not modelled** (designed and measured as Tier 3, SPEC §48, not built).
- Dwell time is preserved, never compressed. Holds are capped at `max_hold`; beyond that a train is UNASSIGNED with a reason.
- A train at a platform can take a departure delay but not an arrival delay. No midnight wrap; minute granularity.
- No passenger-connection or crew constraints.
- The parser handles delays and closures only. The regex fallback reads English and romanised Hinglish; Devanagari is read only by the LLM path. Numbers not written as digits in the message ("तीस मिनट", "half an hour") are always shown as *needs clarification*. On the 3B model, Devanagari number words are often misread, which is why that rule exists.
- The LLM explanation is English only; Hindi and Marathi use grounded templates.
- **Hindi and Marathi strings were drafted without a native speaker and must be reviewed by one before use** (SPEC §37).
- Speech-to-text is optional (`pip install faster-whisper==1.2.1 av==14.2.0`, `RAILFLOW_STT=1`; the `small` model, ~460 MB, downloads on first use). `tools/check_radio.py` with the real model (2026-10-11): the English clip is transcribed almost word for word and yields *delay 11209 +30*, but the closure times came out as "141530", so the closure must be corrected in the text box before parsing; the Hindi clip is not usable with `small`. The transcript is always editable and never parsed on its own. The clips use a synthetic voice. Record with **Record / Stop**; a clip can be played back, deleted and recorded again (60 s maximum).
- Fictional data; not validated against a real division's working timetable. Advisory only; not safety-certified.
- Authentication is demo-grade (password + server-side session, no MFA/SSO); HTTPS only behind a production reverse proxy. Single-node SQLite.
- drei's text renderer bundles a CDN URL as an unused fallback default; RailFlow configures it to a same-origin path and the CSP (`default-src 'self'`) blocks any external request.

MIT licence — see [LICENSE](LICENSE).
