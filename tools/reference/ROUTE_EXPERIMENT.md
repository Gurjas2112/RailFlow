# Route-conflict experiment (generated)

Model: arrival route 3 min before arrival, departure route 2 min after departure; PF 5 is a west-end bay.

Route conflicts in `timetable_normal.json` as scheduled: **7**

- W throat · 51210 UP_DEP PF 2 (13:30–13:32) × 61305 UP_DEP PF 5 (13:30–13:32)
- W throat · 11214 UP_DEP PF 1 (13:55–13:57) × 61307 UP_DEP PF 5 (13:55–13:57)
- E throat · 11216 UP_ARR PF 4 (13:55–13:58) × 51218 UP_ARR PF 2 (13:57–14:00)
- W throat · 51218 UP_DEP PF 2 (14:20–14:22) × 51219 DN_ARR PF 3 (14:19–14:22)
- E throat · 51219 DN_DEP PF 3 (14:27–14:29) × 12222 UP_ARR PF 1 (14:27–14:30)
- E throat · 11217 DN_DEP PF 3 (15:02–15:04) × 51226 UP_ARR PF 2 (15:02–15:05)
- E throat · 12230 UP_ARR PF 1 (15:12–15:15) × 51222 UP_ARR PF 4 (15:12–15:15)

CP-SAT with route constraints (stages: weighted delay → changes): [('OPTIMAL', 16), ('OPTIMAL', 4)]

Route conflicts after solving: **0** · platform conflicts: re-check with the main validator

Changes:

- 61305 (MEMU DN): P5 → P5, held 2 min
- 61307 (MEMU DN): P5 → P5, held 2 min
- 51218 (PAS UP): P2 → P2, held 1 min
- 51219 (PAS DN): P3 → P1, held 0 min
- 12222 (SF UP): P1 → P2, held 0 min
- 51215 (PAS DN): P2 → P3, held 0 min
- 11217 (MEX DN): P3 → P1, held 0 min
- 51222 (PAS UP): P4 → P4, held 3 min
