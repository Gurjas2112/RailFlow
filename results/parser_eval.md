# Parser evaluation (measured)

52 labelled messages from `data/parser_eval.jsonl` (10 Devanagari, 2 radio transcripts). LLM: local Ollama `qwen2.5:3b-instruct`, temperature 0, 8 s timeout. An event counts only if the deterministic proposal validator accepts it with exactly the labelled fields.

| Path | Event precision | Event recall | Exact-match messages | Correct rejections (unknown IDs) | Wrong values flagged for clarification | Median latency |
|---|---|---|---|---|---|---|
| regex | 1.00 | 0.65 | 36/52 | 5/6 | 0/0 | 0 ms |
| llm | 0.82 | 0.80 | 44/52 | 6/6 | 9/9 | 3613 ms |

Exact-match by category:

| Category | regex | llm |
|---|---|---|
| bad_platform | 2/2 | 2/2 |
| clean | 12/12 | 12/12 |
| departure | 3/3 | 3/3 |
| devanagari | 1/10 | 5/10 |
| hinglish | 3/4 | 3/4 |
| multi | 5/5 | 5/5 |
| noise | 3/3 | 3/3 |
| paraphrase | 3/8 | 8/8 |
| radio | 1/2 | 0/2 |
| unknown_train | 3/3 | 3/3 |

## Misses — regex (16)

| Id | Category | Message | Expected | Accepted |
|---|---|---|---|---|
| P13 | paraphrase | 11236 is half an hour behind | [('delay', '11236', 30, 'arrival')] | [] |
| P16 | paraphrase | Delay of 35 minutes reported for 11236 | [('delay', '11236', 35, 'arrival')] | [] |
| P17 | paraphrase | 12233 lost 12 min near the ghat section | [('delay', '12233', 12, 'arrival')] | [] |
| P19 | paraphrase | PF 2 will not be available from 15:00 till 15:45, OHE work | [('closure', 'P2', '15:00', '15:45')] | [] |
| P20 | paraphrase | Engineering block on platform 4 between 13:40 and 14:20 | [('closure', 'P4', '13:40', '14:20')] | [] |
| P27 | hinglish | 12230 15 minute der se aa rahi hai | [('delay', '12230', 15, 'arrival')] | [] |
| P41 | devanagari | गाड़ी संख्या 11209 तीस मिनट देरी से चल रही है | [('delay', '11209', 30, 'arrival')] | [] |
| P42 | devanagari | प्लेटफॉर्म 3 दो बजे से साढ़े तीन बजे तक बंद | [('closure', 'P3', '14:00', '15:30')] | [] |
| P43 | devanagari | गाड़ी ११२१७ २० मिनट देरी से | [('delay', '11217', 20, 'arrival')] | [] |
| P44 | devanagari | 51215 पंद्रह मिनट लेट है | [('delay', '51215', 15, 'arrival')] | [] |
| P45 | devanagari | प्लेटफॉर्म 4 15:00 से 16:00 तक बंद रहेगा | [('closure', 'P4', '15:00', '16:00')] | [] |
| P46 | devanagari | 11209 तीस मिनिटे उशिरा, फलाट ३ दुपारी २ ते ३:३० बंद | [('closure', 'P3', '14:00', '15:30'), ('delay', '11209', 30, 'arrival')] | [] |
| P47 | devanagari | गाडी ११२२५ दहा मिनिटे उशिरा आहे | [('delay', '11225', 10, 'arrival')] | [] |
| P48 | devanagari | फलाट 2 15:00 ते 15:45 बंद राहील | [('closure', 'P2', '15:00', '15:45')] | [] |
| P49 | devanagari | 51218 सुटण्यास 25 मिनिटे उशीर | [('delay', '51218', 25, 'departure')] | [] |
| P52 | radio | शिवनेरी कंट्रोल, गाड़ी संख्या 11209 तीस मिनट देरी से चल रही है। प्लेटफॉर्म 3 दो बजे से साढ़े तीन बजे तक बंद। ओवर। | [('closure', 'P3', '14:00', '15:30'), ('delay', '11209', 30, 'arrival')] | [] |

## Misses — llm (8)

| Id | Category | Message | Expected | Accepted |
|---|---|---|---|---|
| P25 | hinglish | PF 3 band hai 2 baje se 3:30 tak | [('closure', 'P3', '14:00', '15:30')] | [('closure', 'P3', '02:00', '03:30')] |
| P41 | devanagari | गाड़ी संख्या 11209 तीस मिनट देरी से चल रही है | [('delay', '11209', 30, 'arrival')] | [('delay', '11209', 20, 'departure')] |
| P42 | devanagari | प्लेटफॉर्म 3 दो बजे से साढ़े तीन बजे तक बंद | [('closure', 'P3', '14:00', '15:30')] | [('closure', 'P3', '14:00', '15:00')] |
| P44 | devanagari | 51215 पंद्रह मिनट लेट है | [('delay', '51215', 15, 'arrival')] | [('delay', '51215', 5, 'arrival')] |
| P46 | devanagari | 11209 तीस मिनिटे उशिरा, फलाट ३ दुपारी २ ते ३:३० बंद | [('closure', 'P3', '14:00', '15:30'), ('delay', '11209', 30, 'arrival')] | [('closure', 'P3', '02:00', '03:30'), ('delay', '11209', 20, 'departure')] |
| P47 | devanagari | गाडी ११२२५ दहा मिनिटे उशिरा आहे | [('delay', '11225', 10, 'arrival')] | [('delay', '11225', 100, 'departure')] |
| P51 | radio | Shivneri control, section controller here. Train 11209, Shivneri Fort Express, running 30 minutes late. Platform 3 shut, 14:00 to 15:30, for track inspection. Over. | [('closure', 'P3', '14:00', '15:30'), ('delay', '11209', 30, 'arrival')] | [('delay', '11209', 30, 'arrival')] |
| P52 | radio | शिवनेरी कंट्रोल, गाड़ी संख्या 11209 तीस मिनट देरी से चल रही है। प्लेटफॉर्म 3 दो बजे से साढ़े तीन बजे तक बंद। ओवर। | [('closure', 'P3', '14:00', '15:30'), ('delay', '11209', 30, 'arrival')] | [('closure', 'P3', '14:00', '15:00'), ('delay', '11209', 20, 'departure')] |
