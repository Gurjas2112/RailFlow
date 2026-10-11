# Screenshots and screen recording

These were captured from the running RailFlow app (fictional Shivneri Junction) in headless Edge. The desktop shots are 1366×768, the tablet shots 768 px and the phone shots 360 px wide. The app ran against a fresh demo database and used the local Ollama `qwen2.5:3b-instruct` model.

**Full recording:** [`railflow_full_demo.mp4`](railflow_full_demo.mp4) is about 2 minutes of H.264. It walks through flows 01–11 in order on desktop, then shows the tablet and phone layouts.

| Flow | What it shows |
|---|---|
| [`01_login_and_roles/`](01_login_and_roles/) | Invite-only sign-in and the controller workspace |
| [`02_scheduled_conflicts/`](02_scheduled_conflicts/) | S3: the timetable is checked as scheduled. All 3 planted conflicts are found and reported with minutes (GAP P1 2 · GAP P2 3 · OVERLAP P4 5/10), both in the list and on the Gantt chart |
| [`03_assign_platforms/`](03_assign_platforms/) | S1: platforms assigned for the whole day. Result is VALID · FULLY ASSIGNED |
| [`04_disruption_ai_parser/`](04_disruption_ai_parser/) | S2: a radio report is parsed by the local LLM into delay and closure proposals, each linked to the words it came from |
| [`05_replan_compare_apply/`](05_replan_compare_apply/) | Revisions A (min delay), B (fewest changes) and the greedy baseline are compared. Shows the grounded explanation, the Apply step and the before ⇄ after view |
| [`06_rejections_and_faults/`](06_rejections_and_faults/) | S2-late (the train is already at its platform) and S4 (unknown train) are rejected. S5: an injected planner fault is caught (NOT VALID) and Apply is disabled |
| [`07_tradeoff_and_cascade_s8/`](07_tradeoff_and_cascade_s8/) | S8: the departure-delay cascade, the trade-off table, and a reason card showing the chain 51218 → 51215 |
| [`08_3d_and_top_view/`](08_3d_and_top_view/) | 3D station view, before/after comparison, and the 2D top view |
| [`09_roles_and_admin_dashboard/`](09_roles_and_admin_dashboard/) | Read-only viewer screen. A viewer's Apply and an admin's Plan are both refused with 403. Also the admin dashboard, the users page and audit-chain verification |
| [`10_languages/`](10_languages/) | The same screen in English, Hindi and Marathi |
| [`11_responsive/`](11_responsive/) | Tablet (768 px) controller and phone (360 px) viewer layouts |
