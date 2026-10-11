# Screenshots and screen recording

These were captured from the running RailFlow app (fictional Shivneri Junction) in headless Edge. The desktop shots are 1366×768, the tablet shots 768 px and the phone shots 360 px wide. The app ran against a fresh demo database and used the local Ollama `qwen2.5:3b-instruct` model.

**Full recording:** [`railflow_full_demo.mp4`](railflow_full_demo.mp4) is about 2 minutes of H.264. It walks through flows 01–11 in order on desktop, then shows the tablet and phone layouts.

**New-features recording:** [`railflow_new_features.mp4`](railflow_new_features.mp4) is about 80 seconds at 1366×768, with a caption for each step. It covers flows 12–14: uploading your own station, entering a station and trains by hand, and recording a radio report that is transcribed by the local Whisper `small` model.

Flows 01–11 were captured before those features were added, so their Disruption panel still shows the old *Hold to record* button and no editor under the upload box.

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
| [`12_own_station_upload/`](12_own_station_upload/) | The Excel and JSON templates under the upload box. The template station (Sahyadri Road, 3 platforms, 8 trains) loads with its 2 planted conflicts found, then assigns VALID. A typed closure and delay are parsed and replanned; the goods train that only fits the closed platform is UNASSIGNED with its reason. The 3D view is built from the 3 platforms |
| [`13_manual_entry/`](13_manual_entry/) | A station and 3 trains typed in by hand. A bad departure time is flagged per row in plain words before anything loads. After the fix it loads through the same server checks, the clock starts before the first train, the 3-min gap is found and Assign resolves it VALID |
| [`14_radio_recording_and_stt/`](14_radio_recording_and_stt/) | Record and Stop with a timer, then play back, delete or record again. The demo radio clip is transcribed by Whisper `small` on the CPU. Parse takes the delay 11209 +30 as *ready*, but flags the closure as *needs clarification* because Whisper wrote its times as "141530". The operator corrects it; nothing is guessed |
