# CarePath AI — SPEC

| | |
|---|---|
| Status | **v1.28**. v1.0 was frozen as tag `spec-v1` on 28 Oct 2026 (delivery plan, step 1.9); v1.1 adds C14 (D32, step 1.22), v1.2 adds C15 (D33, step 1.23), v1.3 adds C16 (D34, step 1.24), v1.4 adds C17 (D35, step 2.1), v1.5 adds C18 (D36, step 2.2), v1.6 adds C19 (D37, step 2.3), v1.7 adds C20 (D38, step 2.4), v1.8 adds C21 (D39, step 2.8), all proposed 28 Oct 2026; v1.9 adds C22 (D40, step 2.16), v1.10 adds C23 (D41, step 2.21), v1.11 adds C24 (D42, step 2.9), v1.12 adds C25 (D43, step 2.17), v1.13 adds C26 (D47, step 2.30), proposed 29 Oct 2026; v1.14 adds C27 (D48, step 2.5), v1.15 adds C28 (D49, step 2.28), v1.16 adds C29 (D50, step 2.10), v1.17 adds C30 (D51, step 2.18), v1.18 adds C31 (D52, step 2.12), v1.19 adds C32 (D54, step 2.13), proposed 30 Oct 2026; v1.20 adds C33 (D55, Verifier), v1.21 adds C34 (D56, step 2.27), v1.22 adds C35 (D57, step 2.6), v1.23 adds C36 (D58, step 2.14), v1.24 adds C37 (D59, step 2.20), v1.25 adds C38 (D60, step 2.29), proposed 2 Nov 2026; v1.26 adds C39 (D61, decided 2 Nov 2026); v1.27 adds C40 (D62, step 2.10), proposed 2 Nov 2026; v1.28 adds C41 (D63, decided 2 Nov 2026, phase 4); v1.29 adds C42 (D65, Bed Finder under D64), proposed 3 Nov 2026. Changes follow §0 |
| Last updated | 3 Nov 2026 |
| Owner | R5. Every section has a co-owner who signs it off (§0) |
| Sources | [Solution Plan](../docs/CarePath-AI-Solution-Plan.pdf) §6–§9 and §13; [Delivery Plan](../docs/DELIVERY_PLAN.md) |
| Rule | Nobody builds against anything that is not in this file. Whoever waits on another part works with fixtures of the same shape (`testing/fixtures/`, step 1.23) |

## 0. Sign-off and change control

Every section was signed off by Bojan as lead on 28 Oct 2026, under D26 (he approves for the team); the TL reviewed the draft the same day.

| Section | Co-owner | Signed off |
|---|---|---|
| §2 Conventions, §3 Data | R1 | ☑ 28 Oct 2026 |
| §4 Pathway model | R2 | ☑ 28 Oct 2026 |
| §5 State and views | R2, R4 | ☑ 28 Oct 2026 |
| §6 Tools | R3 | ☑ 28 Oct 2026 |
| §7 Actions and autonomy | R3 | ☑ 28 Oct 2026 |
| §8 LLM gateway | R3 | ☑ 28 Oct 2026 |
| §9 Simulation runtime | R1, R2 | ☑ 28 Oct 2026 |
| §10 API and WebSocket | R4 | ☑ 28 Oct 2026 |
| §11 Acceptance criteria | all | ☑ 28 Oct 2026 |

After `spec-v1`, a change needs: agreement at a sync, an entry in the decision register (delivery plan §11), a version bump at the top of this file, and updated fixtures in the same commit (delivery plan, D20).

### Changes vs Solution Plan (C1–C13 accepted in `spec-v1`; C14–C38, C40 and C42 proposed in v1.1–v1.25, v1.27 and v1.29; C39 and C41 decided in v1.26 and v1.28)

| # | Change | Why |
|---|---|---|
| C1 | Event types `TELEMON_START`, `BOOKING`, `CALL`, `REMINDER` added to `events` | The pathway JSON already uses `TELEMON_START`; waits cannot be computed without bookings; call and reminder outcomes must be visible on Maria's timeline |
| C2 | One DuckDB file per **run**; a run = scenario × arm (baseline or agents) × levers | Keeps scenarios and arms isolated; "with and without agents" and what-if use the same code; `scenario_truth` cannot leak through a shared database |
| C3 | Action type `reminder` added | Step 1 of the escalation ladder is an automatic reminder; the Solution Plan action list has no type for it |
| C4 | Supporting tables `comuni`, `mmg`, `bed_occupancy` | Needed by the map, the MMG-group pattern and Bed Finder; implied but not listed in Solution Plan §6 |
| C5 | Every tool result carries a `source` block | The Verifier re-runs exactly the call behind a claim (AC10) |
| C6 | Maria has the fixed ID `p_00001` in every scenario | AC14 and the demo script reference her directly |
| C7 | Every DOUBLE that a tool, view or API returns is rounded (§2), and a test checks that tools return identical bytes | DuckDB's parallel aggregation is not bit-stable (measured 27 Oct 2026, §2). The cache key hashes tool results (§8), so one changed last bit is a cache miss, and in `cache_only` a missing investigation has no fallback |
| C8 | `adherence_by_group` gets a `measure` argument; segments and metrics for `compare_segments` and `risk_drivers` are defined (§6) | Pattern 3 (telemonitoring dropout in rural comuni) had no tool that returns telemonitoring by comune or segment; segment and metric were undefined in the Solution Plan |
| C9 | Only the 2 runs of the scenario on screen advance after the envelope (no envelope since C37); jump forward continues from the current day; performance budgets beyond AC2 (§9) | Demo pacing and budgets, delivery plan D21 and D22 |
| C10 | Cache completeness check (§8) | Any change to the simulator, engine, tools or prompts after the warm-up can change cache keys; the check finds misses before a rehearsal does |
| C11 | Days before 0 are history: the simulator warms up for 120 days (−120..−1) and keeps those events (§2) | Rules and tools look back 30–180 days; without history, `no_dispense('C03CA01', 30)` would fire for every patient on day 30 |
| C12 (D29) | In the process that runs the simulation, tools get a cursor of the run's single connection instead of their own connection (§6) | DuckDB refuses a second connection to a file already open with another configuration, so `connect_for_tools` cannot open while the tick writes (tested 28 Oct 2026) |
| C13 (D30, D31) | User text fields become language-keyed JSON `{"it": "...", "en": "..."}` and lose the `_it` suffix: `actions.rationale_it` → `rationale`, alert `text_it` → `text`, investigation `result_summary_it` → `result_summary`, `worklist_today.reasons` and `script` likewise | The console is bilingual (D30). Templates fill both keys; for LLM texts the 30B model writes `it` and the 4B model translates it into `en` during the warm-up, both cached (D31) |
| C14 (D32) | Pathway steps get an optional `service` (§4). §5.1 says how a step is evaluated, §5.2 how `kpi_daily` is computed | `due_soon` ("not booked") and `next_booked_day` need to know which `BOOKING` belongs to which step, and so does `wait_by_hospital(step)` (§6); v1.0 did not say. The mapping lived only in the simulator's config. Without a rule for when a periodic step's clock starts, Maria, who has no BNP in her history, would be "Fuori percorso" from day 1 |
| C15 (D33) | Shapes of `GET /patients/{id}` and of the tick's `kpi` (§10), and the steps of `sankey_flows` (§5.2) | The fixtures (step 1.23) and the first screens (step 1.25) need them; v1.1 said only "timeline of events and actions, state per pathway" and `{...}`. The meaning of `map_comuni` `adherence_pct` and `alarm`, and of `worklist_today` `pathways` and `outcome`, waits for steps 2.2 and 2.4 (Q7); their fixtures use stand-in values |
| C16 (D34) | What each tool computes (§6): booking-to-slot waits, on-time deadlines, the 10 worst groups plus `rest_of_ats`, the `telemonitoring` measure over everyone ever started, `empty_result` for risk until step 2.3 | v1.2 gave names and shapes but not the computations, so two implementations could disagree and the Verifier could not tell which is right. With a 60-day window on the denominator, patients who stopped telemonitoring left the measure and pattern 3 disappeared (measured, scenario 2); hundreds of groups would not fit a prompt |
| C17 (D35) | `GET /patients/{id}` takes an optional `day`: with it, the API answers from a recording in `demo/story/` instead of the live run (§10). The control endpoints return `{scenario, day, speed}` | The demo opens with every run on day 23 (D21), but Maria's story (demo step 1) tells what happens without CarePath up to her readmission on day 47. Recorded once from the baseline run of scenario 2 to day 62 (`uv run python -m engine.story`); a test checks it against the fixture run. The console needs the day and speed after a control call |
| C18 (D36) | `map_comuni` defined (§5.2): `adherence_pct` is the share of enrolled patients who are on track, collected every drug of the pathway in the last 60 days and, if ever on telemonitoring, sent a reading in the last 7 days; `alarm` is `adherence_pct` below 50%; fewer than 10 patients give NULL and no alarm; `risk_mean` and `high_risk_patients` are NULL until Risk (step 2.3). `sankey_flows` is a DuckDB view. Answers SPEC Q7 for the map | Q7 left the map's meaning open. Measured on all 3 scenarios, 154 comuni, days 35 and 62: `on_track_pct` alone spreads the hidden rural comuni of pattern 3 from rank 8 to 151 and dispensing alone stays at 69–100%; the combined measure ranges 20–91% (the prototype shows 38–76%) and puts them mostly among the 30 worst. The prototype frames exactly the comuni under 50% |
| C19 (D37) | Risk defined (§5.1): the chance of an unplanned admission in the next 30 days; high risk is 0.10 or more; drivers only for high-risk patients. `map_comuni` gets `risk_mean` and `high_risk_patients`; `risk_drivers` returns `{drivers, patients}` over the segment's high-risk patients; both risk tools give `empty_result` only on a run where Risk never ran (§6) | The Solution Plan names XGBoost and top-3 drivers but no label, threshold or tool computation. Measured on seed 42 (not trained on): AUC 0.62 in all 3 scenarios, equal to the simulator's own hazard (0.62), so the 30-day outcome is mostly chance; a 7-day label scored 0.71 but rested on weight gain, which the pathway rule already catches, and ranked patients who left telemonitoring lower. 0.10 marks 1.2% of patients, 19% of whom are admitted within 30 days (7×). TreeSHAP for all 10,000 patients took 500 ms a tick, for the high-risk ones 12 ms |
| C20 (D38) | `worklist_today` defined (§5.2): one list per day, agents arm only, everyone out of hospital with an overdue step or a high risk, ranked by risk; reasons filled by code; `pathways` a list of `pathway_id`s; `outcome` the day's `CALL` code. Pathway steps get a `label` and drugs a name in `drug_names`, both `{"it", "en"}` (§4) | Q7 left `pathways` and `outcome` open, and the list needs history: demo step 9a goes back to day 31's list on day 62. Reasons in two languages name steps and drugs; without names in the pathway file the code would have to name the disease (AC17). On day 30 of scenario 2 the list holds about 2,400 patients; the console shows the top 20 per Centro Servizi (step 2.20) |
| C21 (D39) | Monitoring defined (§4, §5.3): how rules are evaluated and explained, a step's `max_wait_days` for the regional alarm, the tables `deviations` and `alerts`, patient alerts for high-risk patients only, pulls read by `patients_overdue` | The SPEC named Monitoring's outputs but not their rules or storage: "regional alarm when the same deviation exceeds a threshold at one facility" had no threshold, alerts had nowhere to live, and a pulled deadline existed only in memory, so a tool and the engine disagreed on overdue visits (239 against 314, caught by a test). Measured on scenario 2: about 160 new deviations a day, 8 of them of high-risk patients; a 30-day echo threshold alarms on days 29, 33 and 32 in scenarios 1–3 and nowhere else |
| C22 (D40) | `GET /pathways/{pathway_id}` returns the pathway file (§10) | The Percorsi screen (step 2.16) must name steps, and the labels live in the pathway file (C20); no endpoint served them, and labels written into the console would break AC17. The file is returned unchanged, so it is its own fixture |
| C23 (D41) | The pathway file gets `label` `{"it", "en"}` and an optional `readmission_reference` (§4) | The console named the disease itself ("Scompenso cardiaco" in three places) and held the national HF readmission rate (11.87%), so a second pathway would show both wrongly (AC17); `name` is Italian only. The AC17 test now fails if the console contains any name of the pathway file, Maria's story excepted |
| C24 (D42) | Investigator input, loop and answer, and the `investigations` table (§6) | Step 2.9 needs them; the SPEC had only the stream message of one step. Claims point at a step number so every claim keeps the tool call the Verifier repeats; result summaries come from code so no model-written number reaches the stream |
| C25 (D43) | The Investigator runs on the alarm's tick, not asynchronously (§9 step 7); `GET /investigations` (§10) | `free_slots` reads `capacity_slots`, which the tick rewrites every day: an investigation started later would see other numbers, so its cache keys would miss in the demo (SPEC §8). From the cache the alarm's tick takes 0.4–0.7 s, inside AC2; the Chiedi screen (step 2.17) needs the stored investigation |
| C26 (D47) | Group alarms in the pathway file (§4, §5.3), the tool `adherence_by_area` (§6), `alerts.group_alarm` and `group_key`, `alert_id` and `group_key` in the alert message (§10), and the Investigator's opening for a group alarm | Step 2.22 found patterns 2 and 3 in 0 of 3 scenarios: only the echo alarm started an investigation. Measured over days 20–62 of all 3 scenarios (step 2.30): the hidden MMG group collects drugs 86–90% against 98.5% or more for every other group; no single comune shows pattern 3 (0–2 of 4–6 hidden comuni below 50%), but areas of comuni within 12 km, among patients living alone over 40 km away, name 3 of 6, 2–4 of 4 and 3 of 4 hidden comuni with none wrong. With the tool, the worst area is 66–88 points below the rest of the ATS on every day from 0 to 60, and areas of other comuni, of 5–6 patients, up to 54 points from noise alone: the 60-point threshold has a margin of 6 points on both sides. The radius and the 5-patient minimum were picked from 8, 12 and 16 km on these 3 scenarios, and 40 km is the simulator's own threshold for pattern 3 (also the example segment in C8): this is tuned to the scenarios and stated in the limitations |
| C27 (D48) | What-if from full runs computed in advance on a grid (§9), `POST /whatif` reads it (§10), levers `{extra_slots}`; AC4 times the read (§11) | A full run takes 230–317 ms a day per arm (step 2.22), so 6 months of two arms are minutes against AC4's 10 s; a simulator-only run is fast but has no agents in it, and a second, simplified copy of the agents' logic would drift from the real one. D22 had this fallback for a missed AC4; it is the design from the start, like D18 for AC5. The lever's facility and first day come from Monitoring's own alarm, never from `scenario_truth` |
| C28 (D49) | A lever run per scenario in the demo (§9), `lever_run` in the tick message and `GET /capacity` (§10) | D45's before and after needs the agents arm with the proposed lever next to the one without it, and per-facility slot use and waits, which no endpoint gave. Three runs of the scenario on screen took a both-arms p95 of 646–662 ms against 500, so the lever run keeps up at ×1 only and catches up while the clock is paused |
| C29 (D50) | The Investigator answers a free question (§6), `POST /ask` returns the stored investigation or 503 (§10), a tool's error for an unknown field names the allowed ones (§6), and an investigation id is counted when the row is stored | The benchmark (AC6, step 2.10) and Chiedi need questions answered with the tools and no opening; the SPEC had only `POST /ask {question}`. Measured on scenario 2's three yes/no questions: with the answer as the sentence's first word the model began "Sì" with numbers that said no (2 of 3 wrong in two prompt versions); a yes/no field with a "non applicabile" choice got "non applicabile" for all three; code telling the yes/no question and a `Sì`/`No` field first got 3 of 3. The model repeated `{"mmg_group": "coop_12"}` in a segment three times on "Extra inputs are not permitted" alone. A cache miss on one alarm made the next two investigations share an id and stopped the tick |
| C30 (D51) | The shapes of `GET /settings`, `PUT /settings/autonomy` and the approve and reject decisions (§10); the level in force is read from the audit log (§7.3) | SPEC §10 named these endpoints without their shapes, and the console's Approvazioni and autonomy panel (step 2.18) need them. Keeping the levels in the audit log, which §7.3 already requires for every configuration change, adds no table |
| C31 (D52) | The action service's order of checks, guardrail test, daily-limit facility, execution on approval, feedback hand-in and undo (§7.3, §10) | §7.3 listed the checks but not how code applies them; a rejected action should not wait in the queue first, and agent code may not import the simulator (CLAUDE.md rule 5) |
| C32 (D54) | Intervention (§9): tick order (after the Investigator), escalation ladder, warning-sign call, reschedule after a wait alarm, `payload` effects and patient lists (§7.1), rule evidence for patient actions, reminders as one action per problem a day, at most 10 `action` messages a tick; `worklist_today` keeps the top 200 a day (§5.2); a reschedule names `from_facility`, `to_facility` and `service` (guardrail, §7.3) | The SPEC named Intervention's job, not its rules; one action row per SMS cost about 40 ms a tick, and the full worklist's texts another 40, which AC2 had no room for; an action before the Investigator would change the cached alarm investigation |
| C33 (D55) | The Verifier (§6): code only, on the investigation's tick and on `POST /ask`; each claim of `investigations.claims` gets `verified` and `issues`; a step's `verified` on the stream (§10) is all its claims' | The SPEC had the `verified` slot and C5's repeatable call, not the checks. In the 5 answers Chiedi shows, the model's numbers were right but 6 claims gave an ASST's figure as one hospital's and 2 stated a comparison backwards ("83,65% … inferiore al 79,8%"); the 4B translation wrote "4-than" for "40 giorni". An LLM check would need its own cache and could slip the same way |
| C34 (D56) | Action type `capacity_proposal` (§7.2, fixed level 1), Intervention's capacity proposal on the wait alarm (§9), `approved` in the tick's `lever_run` (§10), `capacity_proposal` in the cache manifest (§8) | Step 2.27 needs D45's structural fix as an action to approve; §7.2 had no type for it. Buying capacity is a decision outside the system, so no level lets an agent do it, and approval changes no event: the console turns to the lever run computed in advance (C28) |
| C35 (D57) | PNE forecast to year end (§9 What-if, `src/engine/pne.py`): the what-if runs go on to day 364 and keep `year_end`; `POST /whatif` returns `pne` (§10) | Step 2.6 had no contract. A forecast from the grid's full runs uses the demo's own code and seed (D48), where a fitted trend would be a second model of the same thing; the prototype's "ATS target 12%" has no source, so the line is the pathway's published reference (C23) |
| C36 (D58) | The Reporter (§9): a monthly report on the agents arm, the `reports` table, `GET /reports` and the `report` stream message (§10), `report_days` in the cache manifest (§8), and the tool `pathway_kpi`, which code calls and the model is not offered (§6) | Step 2.14 had only "numbers from views, LLM for sentences". Agents read through tools (rule 3) and no tool returned `kpi_daily`; offering a new one to the model would change every Investigator cache key. The prototype shows the report only as a line in Attività agenti; the lead chose a monthly report with a Panoramica panel, the model's prose cached only for the report the demo shows |
| C37 (D59) | No envelope: the demo opens on scenario 2 and `POST /sim/scenario` is the demo bar's (§9, §10); `GET`/`PUT /sim/cache` for the bar's cache switch; the shape of `GET /reveal/{scenario}`; `GET /worklist` with the patient's age, living alone and comune; the day's call outcomes written back to `worklist_today` after Intervention (§5.2) | Step 2.20 and D44: the envelope is gone and the scenario order is fixed; the cache switch had no endpoint; `/reveal` had no shape; the Centro Servizi calls a person, not an id; and the outcome column stayed empty on screen because the list is built before the calls |
| C38 (D60) | `GET /actions` takes `day` (§10) | Attività agenti (step 2.29) shows the day's actions after a jump or a reconnect, when the stream has none of that day yet; scenario 2 has about 7,000 actions by day 62, too many to read whole every day |
| C39 (D61) | The cost per readmission is the pathway file's `readmission_cost` with its label (§4, §5.2); `kpi_daily.est_readmission_cost_eur` is filled; `POST /whatif` returns `saving_eur` and `cost` (§10) | The prototype and the Solution Plan show euros (steps 6 and 7) and Q2 had no answer; the lead chose a value for the demo. In the pathway file, not in code, because a cost is the disease's (rule 6), and its label travels with every euro figure, so the screen never presents an assumption as a tariff |
| C40 (D62) | `GET /questions` (§10) | Chiedi lists the questions the demo has an answer for (prototype step 5a, "a ready question from the list"); they name the pathway's steps, so the console may not hold them (AC17), and only the manifest knows which are prepared and for which day |
| C41 (D63) | At ×1 the clock stops on the day a wait alarm opens on screen; a reset reopens scenario 2 (§9); the cache warm-up plays the operator's actions of the demo script on the alarm day before any later cached text (§8) | Ten dry runs of the demo through the API (phase 4): the pause landed on day 34 in 6 of 10, where the questions have no prepared answer; the day-59 report was always the template, because the warm-up had not approved what the script approves; and a reset after scenario 3 left scenario 3 on screen |
| C42 (D65) | Bed Finder: `beds` from `src/sim/data/beds.csv`; `bed_occupancy` holds the beds of patients outside the cohort, written once when a run is made (§3.2); `free_beds` takes `pathway_id`, `from_facility` and `patient_id?` and counts the cohort's own inpatients and the day's assignments too, code only (§6); `POST /admissions` runs on request in any run, a baseline run included, and decisions on a bed go to the action's own run in the doctor's name (§7.2, §10) | The Solution Plan names the tables and the tool but not where occupancy comes from: the simulator puts its patients in no ward, and occupancy per tick would cost the tick budget (AC2). Maria's admission of demo step 9c happens only in the run without CarePath. The tool must take the pathway (rule 6) and stay out of the Investigator's tool list, which is part of every cache key (§8) |

## 1. Scope

The PoC monitors heart-failure patients of ATS della Val Padana (ASST Mantova, Cremona, Crema) on synthetic data. Option B adds type 2 diabetes. Everything in this file must work for both pathways without code changes (AC17): a pathway is configuration (§4), not code. Abbreviations follow the glossary in Solution Plan §1.

## 2. Conventions

| Item | Convention |
|---|---|
| Simulated time | Integer `day`; day 0 = start of simulation; 365 days. Days −120..−1 are warm-up history (C11): they are in `events` for lookbacks, while KPIs, alarms and the UI start at day 0. No calendar dates in data; the UI shows "Giorno N" |
| IDs | `p_00001`–`p_13000` patients; `osp_A`, `osp_B`, `osp_C`, `amb_<n>` facilities; `asst_mantova`, `asst_cremona`, `asst_crema`; `mmg_<nnn>`; `coop_<n>` MMG groups; `cs_<n>` Centro Servizi; `act_<run>_<n>` actions; `ev_<n>` events |
| Scenarios | `1`, `2`, `3`. Same pattern types, different locations (Solution Plan §6) |
| Codes | Diagnoses ICD-9-CM, drugs ATC, labs LOINC. The codes in `spec/pathways/` are demo values, not clinically confirmed (delivery plan D28) |
| Units | Days, km, EUR. Rates are fractions 0–1 in data, percentages only in the UI |
| Language | Data and code in English. Every user-facing string (UI, reports, call scripts, rationales) in Italian and English, Italian by default (delivery plan D30). Fields that carry user text are language-keyed `{"it", "en"}` (C13); cached LLM texts are written in Italian and translated into English during the warm-up (D31) |
| Determinism | Every random draw comes from a generator seeded by `(run seed, component)`; same seed, same run, byte for byte (AC14) |
| Numeric precision (C7) | Every DOUBLE that a tool, view or API returns is rounded in SQL after aggregation: fractions and rates to 4 decimals; days, km and kg to 1 decimal; EUR to whole euros. Counts stay integers. Reason: with 8 threads, DuckDB 2.0 returned 12 different `avg(DOUBLE)` results in 12 runs over 2,000,000 rows (differences in the last bits); `round(avg, 4)`, `avg(INTEGER)` and `threads = 1` each gave one result. Below one row group (about 122,000 rows) the results were stable, so small fixtures do not show the problem |
| Missing values | `NULL`, never sentinel numbers |

## 3. Data contracts

One DuckDB file per run: `runs/<run_id>.duckdb` (C2). Static reference tables are generated once per scenario and copied into each run.

### 3.1 `events`

| Column | Type | Notes |
|---|---|---|
| `event_id` | VARCHAR | `ev_<n>`, unique per run |
| `patient_id` | VARCHAR | |
| `day` | INTEGER | |
| `event_type` | VARCHAR | see below |
| `code` | VARCHAR NULL | ICD-9-CM, ATC or LOINC, depending on type |
| `value` | DOUBLE NULL | lab value, weight in kg for readings, scheduled day for `BOOKING` |
| `facility_id` | VARCHAR NULL | |
| `asst_id` | VARCHAR NULL | ASST of `facility_id`; NULL when there is no facility (pharmacy, telemonitoring) |
| `mmg_id` | VARCHAR | patient's MMG at that day |
| `comune_istat` | VARCHAR | patient's comune |
| `source` | VARCHAR | `sim` or `agent_action` |
| `action_id` | VARCHAR NULL | set when `source = agent_action` |

`event_type` values:

| Type | Meaning | `code` | `value` |
|---|---|---|---|
| `DISCHARGE` | hospital discharge | ICD-9-CM main diagnosis | — |
| `ADMISSION` | hospital admission | ICD-9-CM | 1 if unplanned |
| `VISIT` | specialist visit | specialty code | — |
| `IMAGING` | imaging exam, e.g. echo | procedure code | — |
| `LAB` | lab result | LOINC | result |
| `DISPENSE` | pharmacy dispensing | ATC | days of supply |
| `TELEMON_START` | telemonitoring activated (C1) | — | — |
| `TELEMON_READING` | daily reading | — | weight in kg |
| `BOOKING` | exam or visit booked (C1) | service | scheduled day |
| `CALL` | Centro Servizi call (C1) | outcome code | — |
| `REMINDER` | reminder sent to patient (C1) | channel | — |

### 3.2 Reference tables

**`patients`**

| Column | Type | Notes |
|---|---|---|
| `patient_id` | VARCHAR | Maria = `p_00001` (C6) |
| `sex` | VARCHAR | `F`, `M` |
| `age` | INTEGER | at day 0 |
| `comune_istat` | VARCHAR | |
| `asst_id` | VARCHAR | of the comune |
| `mmg_id` | VARCHAR | |
| `lives_alone` | BOOLEAN | |
| `ref_facility_id` | VARCHAR | reference hospital |
| `distance_km` | DOUBLE | to the reference hospital, precomputed (step 1.13) |
| `conditions` | VARCHAR[] | e.g. `['HF', 'T2D']` |

**`comuni`** (C4): `comune_istat`, `name`, `asst_id`, `population`, `population_65plus`, `lat`, `lon`.

**`mmg`** (C4): `mmg_id`, `coop_id` (MMG group), `cs_id` (Centro Servizi), `comune_istat`.

**`facilities`**: `facility_id`, `name` (fictional: "Ospedale A"), `type` (`hospital`, `clinic`), `asst_id`, `comune_istat`, `lat`, `lon`.

**`capacity_slots`**: `facility_id`, `service` (`echo`, `cardio_visit`, `lab`, …), `day`, `slots_total`, `slots_booked`. Free slots = total − booked.

**`beds`** (optional layer): `facility_id`, `ward` (`cardiologia`, `medicina_interna`, `endocrinologia`), `beds_total`. C42: from `src/sim/data/beds.csv`, sized to the cohort's inpatients per hospital (Ospedale A 40, 80, 16; B 28, 56, 10; C 20, 40, 8).
**`bed_occupancy`** (C4, optional layer): `day`, `facility_id`, `ward`, `occupied`, `expected_discharges_next_2d`. C42: the beds taken by patients **outside** the simulated cohort, a share of each ward (`beds` in the simulator config: 40% of cardiology, 62% of internal medicine, 80% of endocrinology) with AR(1) noise from the generator `(seed, "beds")`; `expected_discharges_next_2d` = occupied × 2 ÷ the mean stay (7 days). It depends on nothing the cohort does, so `Simulator.bed_occupancy()` writes the whole horizon once when a run is made, never in the tick. The cohort's own inpatients are not in it: `free_beds` counts them from `ADMISSION` and `DISCHARGE` events.

### 3.3 `scenario_truth`

Stored **outside** the run databases, in `demo/truth/scenario_<n>.json`, generated from `src/sim/scenarios/<n>.json` by `uv run python -m sim.truth`. Only acceptance tests (AC1, AC13) and the Rivelazione screen read it; agent tools have no path to it (step 1.18, enforced by `testing/test_truth_isolation.py`). The `option_b` block is added with option B. Scenario 2:

```json
{
  "scenario": 2,
  "echo_bottleneck": {"facility_id": "osp_B", "asst_id": "asst_cremona"},
  "echo_free_capacity": {"facility_id": "osp_C"},
  "rural_dropout_comuni": ["Poggio Rusco", "Magnacavallo", "Borgocarbonara", "Sermide e Felonica"],
  "low_adherence_group": {"coop_id": "coop_3"},
  "option_b": {"hba1c_gap_group": "coop_5", "enrollment_candidates": ["p_10412", "p_10877"]}
}
```

## 4. Pathway model

One JSON file per pathway in `spec/pathways/`, validated against `spec/pathways/pathway.schema.json` (step 1.3). The schema is generated from the Pydantic model in `src/engine/pathway.py` (`uv run python -m engine.pathway`), and a test fails if they drift apart. The model also enforces the rule language below and checks that every step a rule or an `after` names exists. The heart-failure pathway is `spec/pathways/hf_lombardia_v1.json`:

```json
{
  "pathway_id": "hf_lombardia_v1",
  "name": "PDTA scompenso cardiaco",
  "eligibility": {"any_diagnosis": ["428.*"], "any_drug_atc": ["C03CA01"],
                  "drug_names": {"C03CA01": {"it": "furosemide", "en": "furosemide"}}},
  "status_thresholds": {"due_soon_days": 7, "dropped_after_days": 30, "dropped_if_overdue_steps": 2},
  "steps": [
    {"id": "discharge", "label": {"it": "Dimissione", "en": "Discharge"}, "event": "DISCHARGE", "codes": ["428.*"]},
    {"id": "telemon", "label": {"it": "Telemonitoraggio", "en": "Telemonitoring"}, "event": "TELEMON_START", "due_days": 7, "after": "discharge"},
    {"id": "cardio_visit", "label": {"it": "Visita cardiologica", "en": "Cardiology visit"}, "event": "VISIT", "specialty": "cardiologia", "service": "cardio_visit", "due_days": 30, "after": "discharge"},
    {"id": "echo", "label": {"it": "Ecocardiogramma", "en": "Echocardiogram"}, "event": "IMAGING", "codes": ["88.72"], "service": "echo", "due_days": 90, "after": "discharge"},
    {"id": "lab_bnp", "label": {"it": "Esame BNP", "en": "BNP test"}, "event": "LAB", "loinc": ["30934-4"], "service": "lab", "every_days": 90}
  ],
  "rules": [
    {"id": "weight_gain", "if": "weight_gain_kg_3d >= 2", "then": {"step": "cardio_visit", "due_days": 7}},
    {"id": "no_furosemide", "if": "no_dispense('C03CA01', 30)", "then": {"flag": "adherence_risk"}}
  ],
  "escalation": {"reminder_day": 0, "call_after_days": 3, "mmg_after_days": 7, "high_risk_skips_reminder": true},
  "ward_by_diagnosis": {"428.*": ["cardiologia", "medicina_interna"]}
}
```

**Rule language** (kept small on purpose; the Pathway Builder and Rule Advisor may only emit this):

- Condition: `<feature> <op> <number>` or a function call, joined by `and`.
- Operators: `>=`, `>`, `<=`, `<`, `==`.
- Features: `weight_gain_kg_3d`, `days_since_last_reading`, `days_since_last_dispense(atc)`, `age`, `distance_km`, `risk_score`.
- Functions: `no_dispense(atc, days)`, `overdue(step_id, days)`.
- Actions (`then`): `{"step": id, "due_days": n}` (pull a step earlier) or `{"flag": name}`.

Anything outside this grammar fails validation. That is how a generated pathway or rule is checked before activation.

**Evaluation** (C21, `src/engine/rules.py`): a rule holds for an enrolled patient when every clause does. A feature that does not exist for the patient (no reading ever, so no `days_since_last_reading`) makes its clause false. `no_dispense(atc, n)` holds when the drug was not dispensed in the last `n` days, never included. `overdue(step, n)` holds when the step is overdue by `n` days or more. A `{"flag"}` rule sets the flag in `pathway_state.flags` while it holds. A `{"step", "due_days"}` rule pulls the step when it starts to hold: the step falls due `due_days` later, or stays at an earlier pull, until it is done after the pull day or its clock starts again after the pull day (§5.1: a new anchor for a step with `after`, a new discharge for a periodic step), so a readmission does not leave a visit overdue from before it; the sweep of the next day shows it. Texts that explain a rule are filled from its clauses, their values and the pathway's names ("Peso +2,1 kg in 3 giorni: Visita cardiologica entro 7 giorni"), so a rule needs no label.

**`max_wait_days`** (C21, optional, only on a step with a `service`): a facility whose mean wait for the step, over the bookings of the last 7 days (`wait_by_hospital` with `period_days = 7`), is longer raises a regional alarm (§5.3). HF: echo, 30 days (PDTA §3).

**`group_alarms`** (C26, optional): regional alarms on a group of patients. Each has an `id`, a `label` `{"it", "en"}` for the alarm text, a group `tool` (`adherence_by_group` or `adherence_by_area`, §6) with its `args` (without `pathway_id`) and a `min_gap`: the alarm is open while the tool's worst group is more than `min_gap` below its `rest_of_ats` (§5.3). HF (PDTA §3): drug collection by MMG group, 5 points (pattern 2); telemonitoring of patients living alone over 40 km away, by area, 60 points (pattern 3).

```json
"group_alarms": [
  {"id": "dispensing_mmg_group", "label": {"it": "Ritiro dei farmaci per gruppo di MMG", "en": "..."},
   "tool": "adherence_by_group", "args": {"grouping": "mmg_group", "measure": "dispensing"}, "min_gap": 0.05},
  {"id": "telemon_alone_far", "label": {"it": "Telemonitoraggio di chi vive solo a oltre 40 km, per area", "en": "..."},
   "tool": "adherence_by_area", "args": {"measure": "telemonitoring", "segment": {"lives_alone": true, "distance_km_min": 40}}, "min_gap": 0.6}
]
```

**Pathway label and reference** (C23): `label` `{"it", "en"}` is how the console names the pathway (top bar, Panoramica); `name` stays the Italian title of the PDTA document. `readmission_reference` (optional) is a published 30-day readmission rate `{"rate", "label": {"it", "en"}}`, for HF `{"rate": 0.1187, "label": {"it": "Italia, PNE 2025", ...}}`; the console shows it next to the run's rate. `readmission_cost` (C39, optional) is `{"eur", "label": {"it", "en"}}`, the cost of one readmission and where it comes from (§5.2), and nothing when it is missing.

**Names** (C20): every step has a `label` and every drug of `any_drug_atc` a name in `drug_names`, both `{"it", "en"}`. Texts that name a step or a drug (worklist reasons, call scripts, rationales) take them from here, so no disease is named in code (AC17).

**`service`** (C14, optional) names the capacity service a step is booked in: the `service` of `capacity_slots` and the `code` of its `BOOKING` events. A service belongs to one step of a pathway at most, so every booking maps to one step. The simulator books a step only if it has a service.

**Codes are demo values** (delivery plan D28): ICD-9-CM 428.* for heart failure, procedure 88.72 for echocardiography, ATC C03CA01 for furosemide, LOINC 30934-4 for BNP. They are not clinically confirmed, and the limitations say so. A real deployment would check them, for example BNP against NT-proBNP (LOINC 33762-6), which Italian labs often report.

## 5. State and views

### 5.1 `pathway_state`

One row per patient × pathway in which the patient is enrolled.

| Column | Type | Notes |
|---|---|---|
| `patient_id`, `pathway_id` | VARCHAR | key |
| `enrolled_day` | INTEGER | |
| `enrolled_by` | VARCHAR | `mmg` or `agent` |
| `current_step` | VARCHAR | last completed step |
| `next_step` | VARCHAR NULL | |
| `next_due_day` | INTEGER NULL | |
| `next_booked_day` | INTEGER NULL | from `BOOKING` |
| `status` | VARCHAR | `on_track`, `due_soon`, `overdue`, `dropped` |
| `overdue_steps` | VARCHAR[] | |
| `escalation_step` | INTEGER | 0 none, 1 reminder, 2 call list, 3 MMG notified, 4 ATS alarm |
| `last_event_day` | INTEGER NULL | |
| `risk_score` | DOUBLE | 0–1, from Risk |
| `risk_drivers` | VARCHAR[] | top 3 |
| `flags` | VARCHAR[] | from rules, e.g. `adherence_risk` |
| `updated_day` | INTEGER | |

**Status rules** (thresholds from the pathway JSON):

| Status | Condition | UI label |
|---|---|---|
| `on_track` | nothing due by today is missing | In linea |
| `due_soon` | a step is due within `due_soon_days` and not booked | Scadenza vicina |
| `overdue` | a step is past due and not done | In ritardo |
| `dropped` | overdue more than `dropped_after_days`, or `dropped_if_overdue_steps` or more steps overdue at once | Fuori percorso |

**How steps are evaluated** (C14; `src/engine/state.py`, the same for every pathway):

- A step is done by an event of its `event` type that matches its `codes`, `specialty` or `loinc`. A `TELEMON_START` step is also done by a `TELEMON_READING`, because a patient already on telemonitoring at discharge does not start it again.
- A step with `after` falls due `due_days` after the last event of the `after` step, and stays open until it is done on or after that event's day.
- A periodic step falls due `every_days` after the latest of: its last completion, the last event of a step with neither `after` nor `every_days` (for HF the discharge, so a discharge restarts the clock), and enrolment.
- A step is booked when its service has a `BOOKING` made after the step was last done, for today or a later day. `next_booked_day` is that booked day for `next_step`.
- A step is overdue from the day after its due day. `due_soon` covers due days from today to `due_soon_days` ahead.
- `next_step` is the open step that falls due first. `current_step` is the step whose own event is the most recent; readings do not count.
- Enrolment is the first event that meets the eligibility (`DISCHARGE` or `ADMISSION` with a listed diagnosis, `DISPENSE` of a listed drug), with `enrolled_by = mmg`. Option B needs its own enrolment signal for pattern 5, where eligible patients are not enrolled.
- The state engine never writes `risk_score`, `risk_drivers`, `flags` or `escalation_step`; Risk, Monitoring and the action service own them. A new row starts with 0 and empty lists.

**Risk** (C19; `src/engine/risk.py`, step 2.3) writes `risk_score` and `risk_drivers` on every tick (§9 step 3), for both arms. `risk_score` is the chance of an unplanned `ADMISSION` in the next 30 days, from an XGBoost model trained once on seed 7 with the simulator without a scenario (`models/risk_<pathway_id>.json`, versioned; retraining gives the same bytes). Features come from the state engine and the pathway: age, distance, living alone, days since the last discharge, days since the last dispense of each pathway drug, telemonitoring started, days since the last reading, `weight_gain_kg_3d` (today's reading, or yesterday's, minus the one 3 days earlier, or 4), overdue steps and days overdue. A patient is **high risk** at `risk_score >= 0.10`. `risk_score` is rewritten when the model's score moves by 0.001 or more, or crosses 0.10: every score shifts a little each day as the days since events grow, and writing 6,000 of them a day broke the tick budget (step 2.7). The written value is the score everywhere (map, worklist, tools). `risk_drivers` holds the up to 3 features with the largest positive TreeSHAP contribution for high-risk patients, and is empty for everyone else.

### 5.2 Views

All views are DuckDB views or tables refreshed once per tick and must answer in under 200 ms (AC3).

| View | Grain | Columns |
|---|---|---|
| `kpi_daily` | day × pathway × level (`ats`, `asst`, `comune`) × key | `patients`, `on_track_pct`, `overdue`, `dropped`, `readmissions_30d`, `readmission_rate_30d`, `actions_executed`, `actions_pending`, `est_readmission_cost_eur` |
| `sankey_flows` | pathway × from_step × to_step × status | `patients` |
| `map_comuni` | comune × pathway | `adherence_pct`, `risk_mean`, `high_risk_patients`, `readmission_rate_30d`, `alarm` |
| `worklist_today` | day × patient (all pathways merged, C20) | `rank`, `risk_score`, `reasons` (JSON `{"it", "en"}`, C13), `pathways`, `escalation_step`, `script` (JSON `{"it", "en"}`, filled by Daily Worklist), `outcome` (filled by the operator or the simulation) |

**`sankey_flows`** (C15): `from_step` is `current_step` and `to_step` is `next_step` of `pathway_state`, NULL when the patient has none; `patients` counts the rows with that pathway, both steps and status. It is a DuckDB view (C18). A periodic step leads to itself (on day 62 of scenario 2, `lab_bnp` → `lab_bnp` for 86% of patients), so the console draws two columns, last step done and next step, where a loop is not a cycle.

**`map_comuni`** (C18) is a table the tick refreshes for the current day, one row per comune with enrolled patients of the pathway, by where they live. `adherence_pct` is the share of those patients who meet all of: `status` is `on_track`; every drug in the pathway's `eligibility.any_drug_atc` dispensed in the last 60 days; if they ever started telemonitoring (warm-up included), a `TELEMON_READING` in the last 7 days. The windows are those of the `dispensing` and `telemonitoring` measures (§6). With fewer than 10 patients `adherence_pct` is NULL and `alarm` false; otherwise `alarm` is `adherence_pct < 0.5`, the prototype's low band. `readmission_rate_30d` equals the comune's `kpi_daily` row of the day. `risk_mean` is the mean `risk_score` of the comune's enrolled patients and `high_risk_patients` counts those at high risk (C19); both are NULL only where Risk did not run. Regional alarms from Monitoring (step 2.8) come as `alert` messages, not as map rows.

**`worklist_today`** (C20) is a table with one list per day, kept for every day so the console can show an earlier day's list (demo step 9a). It is built on the tick of the agents arm only (§9 step 6; the baseline arm is without CarePath). A patient is on the list when out of hospital (an `ADMISSION` after the last `DISCHARGE` means in hospital) with at least one overdue step, a high risk (C19) or a pathway rule that holds (C21). `rank` orders by `risk_score`, highest first, then `patient_id`; the top 200 of each day are kept (C32: the texts of all ~2,400 cost the tick about 40 ms, and the Centro Servizi calls from the top). `reasons` is filled by code from the pathway's names (§4): each overdue step with its days late, and for a high-risk patient the chance of admission with the drivers and their values, for example "Rischio alto: 96% di ricovero in 30 giorni (+2,9 kg in 3 giorni, 29,4 km dall'ospedale); Esame BNP in ritardo di 17 giorni". Driver texts are neutral ("ultimo ritiro di furosemide oggi"): a driver says a value raises the risk, not that something is missing. Every rule that holds adds its text (§4), for example "Furosemide non ritirato negli ultimi 30 giorni". `pathways` is the list of `pathway_id`s with a reason. `escalation_step` is the patient's highest in `pathway_state`. `script` is NULL until the Daily Worklist agent (phase 3). `outcome` is the code of the `CALL` event recorded for the patient that day (for example `completed`, `delivery_arranged`), NULL until called; the list is built before Intervention calls (§9 steps 6 and 8), so the tick writes the day's outcomes back after Intervention (C37, step 2.20).

**Readmission, PNE-style:** an unplanned `ADMISSION` within 30 days after a `DISCHARGE` with an HF main diagnosis. Rate = such readmissions ÷ HF discharges in the period. Simplified versus the official PNE protocol; the simplification is listed in the limitations.

**Cost:** `est_readmission_cost_eur = readmissions × readmission_cost_eur`, a single configured parameter. C39: it is the pathway file's `readmission_cost` `{"eur", "label": {"it", "en"}}` (§4), for HF 3,500 euros, a value the lead chose for the demo (D61; Q2 asked for a public source, which is still open), and its label says so next to every euro figure; a pathway without it has the column NULL and no euros.

**`kpi_daily`** (C14) is a table with one row per day from day 0, pathway, level and key. Keys are `ats` for the ATS, `asst_id` and `comune_istat`, by where the patient lives; a unit without enrolled patients has no row. `patients` counts enrolled patients; `on_track_pct` is a fraction (§2) despite its name; `overdue` does not include `dropped`. Readmissions cover the period from day 0 to the row's day: `readmissions_30d` counts unplanned admissions in the period within 30 days after an index discharge (the discharge may be in the warm-up), and `readmission_rate_30d` divides them by the index discharges in the period, or is NULL without discharges. The rate is noisy in the first days (day 0 of scenario 2: 5 of 8). `actions_executed` counts the pathway's actions executed up to that day and `actions_pending` those still `proposed`; an action counts where its patient lives, or only at ATS level when it has no patient.

### 5.3 Monitoring: deviations and alerts (C21)

Monitoring (`src/agents/monitoring.py`, step 2.8) runs on every tick of both arms after Risk (§9 step 4). Rules only, no LLM. It writes `flags`, pulls steps (§4) and fills two tables; it creates no actions (the action service does, step 2.12).

| Table | Columns | One row per |
|---|---|---|
| `deviations` | `day`, `patient_id`, `pathway_id`, `kind` (`rule`, `overdue`), `code` (rule id or step id) | a rule that starts to hold for a patient, or a step that becomes overdue; Intervention acts on them (step 2.13), and the tools read rule pulls from them |
| `alerts` | `alert_id` (`al_<run>_<n>`), `day`, `level` (`patient`, `regional`), `pathway_id`, `patient_id`, `facility_id`, `step`, `group_alarm`, `group_key`, `text` (`{"it", "en"}`), `investigation_id`, `closed_day` | an alert, as pushed on the stream (§10); `group_alarm` and `group_key` belong to a group alarm (C26) |

**Patient alert:** one per high-risk patient (C19) with new deviations that day, naming each with its values; about 8 a day in scenario 2 (D39). All deviations, of every patient, are in `deviations` and in the worklist.

**Regional alarm:** a facility over a step's `max_wait_days` (§4) opens one alarm for that facility and step; it closes (`closed_day`) when the wait is back within the threshold, and a later breach opens a new one. Measured with the 30-day echo threshold: scenario 1 day 29 (Ospedale A), 2 day 33 (Ospedale B), 3 day 32 (Ospedale C); no other facility goes above 3 days. `investigation_id` is set when the Investigator starts (step 2.9).

**Group alarm** (C26): each of the pathway's `group_alarms` (§4) opens one alarm while its tool's worst group is more than `min_gap` below `rest_of_ats`, and closes when it is not, checked on day 0 and every 7 days after: the measures span 60 days of dispensing or 7 of readings, and the two calls cost about 30 ms a tick per arm, which the both-arms budget (§9) has no room for every day. `group_key` is the worst group on the opening day (an MMG group, or an area's first comune), and the text names the group, or all comuni of the area, with both values. One alarm per group alarm, not per group, so an area whose members shift by a comune does not reopen it. The effects of patterns 2 and 3 are in the warm-up history, so both open on day 0, before the demo's start day.

The baseline arm runs Monitoring too, since rules belong to the PDTA; only the agents arm's alerts are pushed.

## 6. Tools

All tools are **read-only**, take typed arguments and return JSON. The Investigator uses only these tools and never writes SQL (Solution Plan §8 guardrails). Tool descriptions shown to the model are in Italian; names and arguments are in English.

Every tool gets its database from `engine.db.connect_for_tools(run_id)` and from nothing else: the run database read-only, with DuckDB's access to files disabled and the configuration locked. A tool therefore cannot read `demo/truth/` or the scenario files, attach another database, or write. Agent code does not import the simulator (step 1.18, tested).

**In the simulation process (C12, delivery plan D29):** while the tick holds a run open for writing, DuckDB refuses any second connection to that file in the same process, `connect_for_tools` included. So the tick opens each run once, with file access disabled and the configuration locked, and tools get a cursor of that connection through `engine.db`. Truth and scenario files stay unreachable (tested); write protection moves from the database to the tools' code, with a guard that runs only `SELECT`/`WITH` statements and a test. `connect_for_tools` stays for notebooks and tests, which read a finished run.

Every result has the same envelope (C5):

```json
{
  "data": {"Ospedale A": 22, "Ospedale B": 41, "Ospedale C": 14},
  "source": {"tool": "wait_by_hospital", "args": {"pathway_id": "hf_lombardia_v1", "step": "echo", "period_days": 90}, "run_id": "s2_agents", "day": 35}
}
```

Errors: `{"error": {"code": "unknown_step", "message": "…"}}`. Codes: `unknown_pathway`, `unknown_step`, `bad_argument`, `empty_result`. A `bad_argument` for an unknown field names the fields allowed where it was, for example `a.mmg_group: Extra inputs are not permitted (campi ammessi: asst_id, comune_istat, coop_id, …)` (C29).

Every number in `data` follows the precision rule in §2. `testing/test_tools_deterministic.py` calls every tool on two fresh connections with default threads, on a full-size run (10,000 patients, 365 days), and asserts identical bytes (C7).

| Tool | Arguments | `data` |
|---|---|---|
| `compliance_by_step` | `pathway_id`, `asst?` | `{step: on_time_fraction}` |
| `wait_by_hospital` | `pathway_id`, `step`, `period_days=90` | `{facility_name: mean_wait_days}` |
| `patients_overdue` | `pathway_id`, `step`, `asst?`, `limit=20` | `{count, patients: [{patient_id, days_overdue, risk_score}]}` |
| `free_slots` | `service`, `asst?`, `horizon_days=21` | `{facility_name: free_slots}` |
| `adherence_by_group` | `pathway_id`, `grouping` (`mmg`, `mmg_group`, `comune`, `age_band`), `measure` (`dispensing`, `telemonitoring`; default `dispensing`, C8), `period_days=60` | `{group: fraction}`, plus `rest_of_ats` |
| `adherence_by_area` (C26) | `pathway_id`, `measure` (default `telemonitoring`), `segment?`, `period_days=60` | `{areas: [{comuni, value, patients}], rest_of_ats}` |
| `readmissions_by_comune` | `pathway_id`, `period_days=180` | `{comune_name: rate}`, sorted descending |
| `risk_drivers` | `pathway_id`, `segment?` | `{drivers: [{name, weight}], patients}` (C19) |
| `compare_segments` | `pathway_id`, `a`, `b` (segments), `metric` | `{a: value, b: value, difference}` |
| `pathway_kpi` (C36, code only) | `pathway_id`, `level` (`ats`, `asst`), `day?` (today by default, not later) | `{key: {patients, on_track_pct, overdue, readmissions_30d, readmission_rate_30d, actions_executed, actions_pending}}`, the `kpi_daily` rows of the day (§5.2). Not offered to the model: `definitions()` leaves out `CODE_ONLY`, because the tool list is part of every Investigator cache key (§8) |
| `eligibility_candidates` (option B) | `pathway_id`, `mmg?` | `{count, patients: [{patient_id, reasons}]}` |
| `free_beds` (C42, code only) | `pathway_id`, `diagnosis`, `from_facility`, `patient_id?`, `asst?` | `{wards, beds: [{facility_id, name, ward, beds_total, free_now, free_in_2d, bed, distance_km}]}`. Like `pathway_kpi`, not offered to the model |

**Measures and metrics (C8, C16):**

- `dispensing`: share of enrolled patients who collected each chronic drug of the pathway within the period.
- `telemonitoring`: share of patients who ever started telemonitoring (warm-up included) who sent at least one reading in the last 7 days; `period_days` does not apply. A patient who stopped long ago still counts as stopped (C16).
- `metric` for `compare_segments` is one of `dispensing`, `telemonitoring`, `readmission_rate_30d`, `on_time_fraction`, `risk_mean`.

**Segment (C8):** a JSON object with any of `asst_id`, `comune_istat` (list), `coop_id`, `age_min`, `age_max`, `lives_alone`, `distance_km_min`. All keys are optional and combine with AND; `{}` is the whole population of the pathway. Example for pattern 3: `{"lives_alone": true, "distance_km_min": 40, "age_min": 75}`.

**What each tool computes (C16, step 1.24).** A tool sees the run up to its day ("today"): the tick's day, or for a finished run the last day of `kpi_daily`.

- `compliance_by_step`: for each step with a deadline, the share of deadlines that fell due in the last 90 days and were met on time. Deadlines follow §5.1: a step with `after` gets one per event of that step; a periodic step gets one per completion, discharge or enrolment. A deadline that a newer anchor replaced before it fell due does not count.
- `wait_by_hospital`: mean days from booking to the booked day, over the `BOOKING`s of the step's `service` (C14) made in the period by patients of the pathway, by the hospital or clinic booked. A step without a service gives `bad_argument`.
- `patients_overdue`: patients with the step overdue today by the rules of §5.1 (the same set as `overdue_steps`), the most overdue first. A deadline a rule pulled earlier counts, read from `deviations` (C21); `compliance_by_step` counts the pathway's own deadlines only.
- `free_slots`: free slots from tomorrow for `horizon_days`. On a live run the tick keeps `capacity_slots` current (step 2.1); on a finished run it is exact only on the last day.
- `adherence_by_group` and `readmissions_by_comune`: at most the 10 worst groups (lowest adherence, highest readmission rate) with at least 10 patients, or 5 index discharges for readmissions; then `rest_of_ats` over every other patient of the pathway, or `null` when all groups are shown. Age bands: `<65`, `65-74`, `75-84`, `85+`. Comuni are named.
- `adherence_by_area` (C26): an area is a comune with every comune whose centroid lies within 12 km of it, pooled over the segment's patients, so a cluster of small comuni shows where no single comune reaches 10 patients. The worst area with at least 5 patients comes first; its comuni are then left out and the next is searched, up to 3 areas, so areas do not overlap. `comuni` are the area's comuni with patients in the segment, by name; `rest_of_ats` is every segment patient outside the shown areas. Values come from integer counts (C7).
- `readmission_rate_30d` over a period: §5.2 with the period's last `period_days` days in place of day 0 to today (180 days for `compare_segments`). `dispensing` and `telemonitoring` use 60 days and `on_time_fraction` pools every deadline of the last 90 days.
- `risk_drivers` (C19): over the segment's high-risk patients today, `weight` is the share whose `risk_drivers` include the driver, most frequent first; `patients` is how many high-risk patients that is. No high-risk patient in the segment gives `empty_result`. The `risk_mean` metric is the mean `risk_score` of the segment's enrolled patients, summed as integers (C7). Both give `empty_result` on a run where Risk never ran (no positive score).
- `free_beds` (C42): `wards` are the pathway file's `ward_by_diagnosis` for the diagnosis, in its order (`bad_argument` when none); `beds` has one row per hospital and ward. A bed is taken by a patient outside the cohort (`bed_occupancy` of the day), by a cohort patient in hospital (last `ADMISSION` with no `DISCHARGE` since, up to today; the simulator puts nobody in a ward, so the patient goes to one of the diagnosis's wards by patient number, `patient_id` itself left out), or by an executed `bed_assignment` whose `payload.day` is today, which holds its own `payload.bed` and takes its patient out of the cohort count. `free_now` = total − taken (not below 0); `free_in_2d` adds `expected_discharges_next_2d`, up to the total; `bed` is the first free bed, with bed numbers 1–total ordered by CRC-32 of `facility/ward/day/bed` (no draw), null when none is free; `distance_km` is great-circle from `from_facility`.
- `eligibility_candidates` comes with option B.

**Investigator** (C24, `src/agents/investigator.py`, step 2.9). Input: a regional alarm's text and step, the pathway file and the run's facilities (name, type, ASST); the system prompt gives the steps, the facilities and a general method, never where a problem is. Code runs the alarm's own evidence first, for the whole ATS: `wait_by_hospital` for the alarm's step over the alarm's 7-day window and `free_slots` for its service; they are steps 1 and 2 and the model sees them as its own calls. For a group alarm (C26) the opening is the call Monitoring made, the alarm's tool with its `args`, as step 1. **A free question** (C29: Chiedi, `POST /ask`, the benchmark of AC6) has no opening, since which tools answer is what the benchmark measures; its prompt (`investigator-ask-v<n>`) says the agent answers an operator's question. Code tells a yes/no question by its form, an Italian question with none of the question words (quale, quanti, dove, chi, come, quando, perché, cosa…); for one, the answer's first field is `risposta`, `Sì` or `No`, decided before the sentences, and code puts it first in the conclusion. Investigation ids count stored rows, so an alarm whose investigation found no answer leaves no gap that a later one could reuse. At most 6 tool calls (steps) in all, one gateway call per turn with `qwen3:30b-instruct` (D11); each tool result goes back to the model with its step number (`passo`). The answer is `{"claims": [{"text", "step"}], "conclusion"}` in Italian, validated against a Pydantic schema; a claim must point at a step whose tool returned `data`, others are dropped, and none left is a failure. `qwen3:4b-instruct` translates claims and conclusion into English (D31). Each step's `result_summary` on the stream (§10) is filled by code from the tool's data, not by the model. The Investigator only reads; whoever runs it stores the row:

| Table | Columns |
|---|---|
| `investigations` | `investigation_id` (`inv_<run>_<n>`), `day`, `pathway_id`, `alert_id`, `question` `{"it", "en"}`, `steps` `[{"step", "tool", "args", "result_summary"}]`, `claims` `[{"text": {"it", "en"}, "step", "verified", "issues"}]` (C33), `conclusion` `{"it", "en"}`, `prompt_version` |

Steps keep the tool and its arguments, not the data, because the Verifier repeats the call (C5).

**Verifier** (C33, `src/agents/verifier.py`, phase 3). Code only, no model. Whoever runs the Investigator runs it right after, on the same cursor and day (§9 step 7, `POST /ask`), so each repeated call returns the bytes the Investigator saw (C7). For every claim it repeats its step's call once and checks the claim's text:

- **Numbers**, Italian and English: each number is in the tool's `data` (a fraction may be written as a percentage, ×100), in the call's arguments, in the names of the data ("weight_gain_3d"), or in the question; it may be rounded or cut to the decimals the text shows, and its sign is free. A number next to a name of the data (a hospital, a comune, a patient id, a step by its id or label, `rest_of_ats` as "resto dell'ATS") must be that name's value or a number of the call: the nearest name before it, or one just after it ("83,65% per l'ecocardiogramma"), with no other number and no sentence end between. Digits inside a name ("Poliambulatorio 5", "coop_6") are not numbers. A threshold the model made up is an issue, since its prompt says every number comes from a tool.
- **Comparisons**, Italian: "inferiore", "superiore", "sotto", "più alto" and their kin hold between the nearest number before (not one of the call) and the first after, of the same unit (`%` or the word after the number), in one sentence. "inferiore di 9,14 punti" states a difference and is not checked.
- **Scope**, Italian: a facility the claim names, on a tool whose data is not per facility, is an issue naming what the figure is for: the ASST of the call's `asst` (or a segment's `asst_id`), else the whole ATS.

Each claim gets `verified` (true without issues, false with any) and `issues` `[{"kind": "number" | "comparison" | "scope", "text": {"it", "en"}}]`, the correction filled by code from the tool's data, for example `34,0: per Ospedale B wait_by_hospital dà 30,4` or `compliance_by_step dà il dato di ASST Cremona, non di Ospedale B`; an issue found only in the English text says so (`(testo inglese)`). The claim's text is not rewritten. A step whose call no longer returns data leaves its claims `verified: null`, `issues: []`, and the console shows them without a badge (Solution Plan §7). Measured on 2 Nov 2026 (AC10) on the 5 answers Chiedi shows: 6 of 18 claims flagged, each a slip read by hand (6 ASST figures given as a hospital's, 2 comparisons stated backwards, 1 translation slip), and each of the 97 numbers changed alone, in the Italian or the English text, caught.

The canonical JSON schemas for these tools live in `src/agents/tools.py` (Pydantic models, Italian descriptions, `$ref`s inlined) and are the single source for the agents. `testing/llm_eval.py` moves to them with the LLM gateway (step 2.7) and is measured again there; its stored results (step 0.4) used its own copy. Benchmark questions are answered with these tools too, not with SQL (Solution Plan §8 allows text-to-SQL for them, but §4 puts text-to-SQL out of scope; C16).

## 7. Actions and autonomy

### 7.1 `actions`

| Column | Type | Notes |
|---|---|---|
| `action_id` | VARCHAR | |
| `agent` | VARCHAR | `intervention`, `enrollment_advisor`, `pathway_builder`, `rule_advisor`, `daily_worklist`, `bed_finder` |
| `type` | VARCHAR | see §7.2 |
| `patient_id` | VARCHAR NULL | NULL for actions on a scope |
| `scope` | JSON NULL | e.g. `{"facility_id": "osp_B", "patients": 18}` |
| `pathway_id` | VARCHAR NULL | |
| `payload` | JSON | type-specific, e.g. `{"from_facility": "osp_B", "to_facility": "osp_C", "day": 39}` |
| `rationale` | JSON | `{"it": "...", "en": "..."}` text for the UI (C13) |
| `evidence` | JSON | list of tool `source` blocks that support the action |
| `autonomy_level` | INTEGER | level in force when created |
| `status` | VARCHAR | `proposed`, `approved`, `executed`, `rejected`, `undone` |
| `created_day`, `executed_day` | INTEGER | |
| `decided_by` | VARCHAR NULL | `auto`, or the user who approved or rejected |

### 7.2 Types and default autonomy

Levels (Solution Plan §8): 0 observe, 1 propose, 2 do with approval, 3 do alone. The demo starts from these defaults; in demo step 6 the manager raises `reschedule` and `notify_mmg` to 3.

| Type | Agent | Default level | Can be raised to 3 |
|---|---|---|---|
| `reminder` (C3) | Intervention | 3 | — |
| `call_task` | Intervention, Daily Worklist | 3 | — |
| `notify_mmg` | Intervention | 2 | yes |
| `reschedule` | Intervention | 2 | yes |
| `enroll_proposal` | Enrollment Advisor | 3, MMG notified, MMG can undo | — |
| `pathway_proposal` | Pathway Builder | 3 after automatic checks, clinical board notified | — |
| `rule_proposal` | Rule Advisor | **1, fixed**: the manager always approves | no |
| `capacity_proposal` (C34) | Intervention | **1, fixed**: buying capacity is the manager's decision outside the system | no |
| `bed_assignment` | Bed Finder | 3 (alternative mode: 2 with doctor confirmation) | — |

**Bed Finder** (C42, `src/agents/bed_finder.py`, D64). Whether to admit is the doctor's decision; the agent only chooses where, on request (`POST /admissions`), never in the tick. Code ranks the rows of `free_beds` that have a bed free now or in 2 days: free now first, then the emergency department's own hospital, then the nearest, then the wards in the file's order, then the facility id; the first three are the candidates. The first with a bed free now becomes one `bed_assignment`: `scope` `{facility_id}`, `payload` `{day, from_facility, facility_id, facility_name, ward, ward_label: {"it", "en"}, bed, choice, candidates}` (no diagnosis, guardrail 1), the tool's `source` as evidence, a template rationale filled by code (D17). Level 3 executes it at once; level 2 leaves it `proposed` and the bed free until the doctor confirms (AC19). `choice` > 0 is the doctor's pick among the candidates: it is approved at once in the doctor's name. A bed is no simulation event: the emit is empty. The level holds for both arms (`PUT /settings/autonomy` writes `bed_assignment` into the baseline runs too), because Bed Finder serves the hospitals, also without CarePath.

### 7.3 Action service

The only component that writes state (delivery plan, principle 4). For every action it checks, in order:

1. **Guardrails that cannot be switched off:** no therapy change, no diagnosis, no decision on *whether* a patient needs an exam or an admission (only *where* and *when*).
2. **Autonomy level** for the type: below 3 the action waits in the approval queue.
3. **Daily limit** of automatic actions per facility (configurable, default 50).
4. **Evidence present:** an action without at least one tool `source` is rejected.

It then executes the action, writes the audit log, emits the effect as events for day D+1 through the simulator feedback hook (§9), and pushes an `action` message on the WebSocket. `undo` on an executed action writes a compensating event and sets the status to `undone`.

**In code** (C31, `src/agents/actions.py`, step 2.12): checks 1 and 4 reject (status `rejected`, `decided_by` `action_service`, the reason in the `rejected` entry's `details`) and run before 2 and 3, which queue (status `proposed`, the reason in the `created` entry's `details`), so an action that may never run does not wait for a decision. Guardrail 1 is checked on the action's fields: a type without a level in §7.2, a `payload` or `scope` key naming a therapy or a diagnosis (`therapy`, `drug`, `dose`, `atc`, `prescription`, `diagnosis`, `icd`, `icd10`), or a `reschedule` without `from_facility`, `to_facility` and `service` (it moves existing bookings and never books a new exam; C32) is rejected. The daily limit counts actions executed with `decided_by = 'auto'` that day at the facility of `scope.facility_id`, else `payload.from_facility` or `payload.facility_id`; an action without a facility has no limit. An approved action is executed at once, on the run's current day. The feedback hook is handed in by the engine (`Run.feedback`), since agent code never imports the simulator; the simulator applies the payload's effects (C32, `src/sim/README.md` §9). The compensating event of `undo` is not built yet: the demo shows no undo of an effect. Action ids are `act_<run_id>_<n>`, n counting stored rows.

**Audit log** (`audit_log`): `ts_day`, `action_id`, `event` (`created`, `approved`, `rejected`, `executed`, `undone`, `config_changed`), `actor`, `details` JSON. Every configuration change (autonomy, rules, pathways) is logged with its author.

## 8. LLM gateway

One function used by every agent (delivery plan, step 2.7):

```python
complete(agent: str, prompt_version: str, messages: list, *, tools=None, schema=None, model: str) -> GatewayResult
```

| Rule | Value |
|---|---|
| Sampling | temperature 0, fixed seed, context `num_ctx` 8192 (Ollama's default 4096 cut the Investigator's prompt, C24) |
| Output | JSON schema enforced through Ollama structured output whenever `schema` is given; validated after the call |
| Retry | 1 retry on invalid output |
| Timeout | 20 s, then fall back to the cache; 600 s in warm-up runs that fill the cache |
| Models | `qwen3:30b-instruct` for cached outputs, `qwen3:4b-instruct` for short live text (delivery plan, D11); `keep_alive` keeps the model in use loaded |
| Cache scope | only outputs the demo script shows, listed in `demo/cache/manifest.json`; everything else uses the agent's template (delivery plan, D17) |
| Cache key | SHA-256 of `(agent, model, prompt_version, canonical JSON of messages, tools, schema)`. Canonical JSON: keys sorted, no whitespace, UTF-8, numbers as tools return them after rounding (§2) |
| Cache completeness (C10) | `testing/test_cache_complete.py` (marker `demo`) plays the demo script through the API in `cache_only` mode and fails on any cache miss; with C41 it plays the operator's approvals and autonomy change of the script on the alarm day too, since they change every later cached text's inputs. It runs after every change to the simulator, engine, tools or prompts once a cache exists, and before every rehearsal. A miss is fixed by `uv run python testing/cache_warmup.py --live`, which plays the same script in `cache_first` and fills only the missing entries (step 2.11). The Investigator has no template fallback (Solution Plan §8), so this check is its guard |
| Cache store | `demo/cache/<agent>/<key>.json` |
| Modes | `live` (call, then cache, overwriting what is there), `cache_first` (development, rehearsals and warm-ups, which fill only misses: the 30B model on CPU does not give the same bytes twice, so `live` would change answers already checked, step 2.10), `cache_only` (default at demo start, D14; the operator hotkey toggles it) |
| Log | one line per call in `logs/llm.jsonl`: `ts`, `agent`, `model`, `prompt_version`, `key`, `mode`, `cache_hit`, `latency_ms`, `valid`, `retries` |

**In code** (`src/agents/llm.py`, step 2.7): `schema` is a Pydantic model; its JSON schema is what goes to Ollama and into the cache key, and the answer is validated with the model. The retry repeats the messages with the invalid answer and a note on what was wrong, since at temperature 0 the same messages give the same answer. When no valid answer can be had (a miss in `cache_only`, a timeout, two invalid answers, Ollama down), `complete` raises `LLMUnavailable` and the agent uses its template. `live` overwrites the cache entry; the other modes read it first.

**Thinking models:** the gateway always sends `think: false`. Models that cannot turn thinking off (for example the plain `qwen3:4b` and `qwen3:30b` tags) are not allowed; use the `-instruct` tags.

## 9. Simulation runtime

**Run:** `run_id = s<scenario>_<arm>[_<lever-hash>]`, for example `s2_agents`, `s2_baseline`, `s2_agents_echo+1`. A run is one simulator instance with its own seed stream and its own DuckDB file. Demo start launches six runs, 3 scenarios × 2 arms, replays them to the start day (day 23) and pauses (delivery plan, D21). Only the 2 runs of the scenario on screen advance; the other 4 stay paused (C9). There is no envelope (D44, C37): the demo opens on scenario 2 and the operator's demo bar takes the scenarios in the order 2, 1, 3. The screen shows one scenario; the arm switch drives Confronto and "Senza CarePath".

**Lever runs** (C28, step 2.28, D45). When a scenario's what-if grid exists (§9 What-if), the demo also holds the agents arm with the lever the grid proposes: the smallest number of extra slots whose 6-month mean wait is within the step's `max_wait_days` (`whatif.proposed_lever`; +2 in scenario 1, +1 in 2 and 3). It is built and replayed to the start day with the others (9 runs, 68 s on a warm laptop, peak 1.9 GB) and is the agents run day by day until the lever starts. At ×1 it advances with the two arms (three runs at most 548 ms a day, within the 2 s); at ×4 it waits, because three runs do not fit the 500 ms budget, and while the clock is paused it catches up a day at a time. The tick message says how far it is (§10). Its run id is the grid's, `s<n>_agents_<service>+<k>`, and every read endpoint takes it as `run`.

**Tick order for day D** (Solution Plan §9):

1. The simulator emits events for day D, including the effects of actions executed on day D−1.
2. The state engine updates `pathway_state` for patients with new events and sweeps deadlines for all.
3. Risk rescores patients with new events.
4. Monitoring applies pathway rules and approved Rule Advisor rules; raises patient deviations and regional alarms.
5. Views refresh.
6. Daily Worklist builds the list at the start of the day.
7. On a regional alarm, the Investigator runs on the same tick, after `capacity_slots` is written, so its tools see the alarm's day and its cache keys match the warm-up (C25); from the cache it takes well under a second. It stores the row, sets the alarm's `investigation_id` and adds its steps to the day's messages; with no answer (a cache miss) the alarm stays without one and the tick goes on. The Verifier checks its claims first, on the same cursor and day (C33).
8. Intervention handles the day's deviations and open alarms through the action service (C32), after the Investigator: the alarm is explained on the day as it was, then agents act (D53). If a reschedule ran, `capacity_slots` is written again.
9. The WebSocket pushes the new state, alarms and actions. On the last day of a month (days 29, 59, …) the agents arm's Reporter first writes the month's report (C36), after Intervention.

**Reporter** (C36, `src/agents/reporter.py`, step 2.14). Code reads the month's numbers through the tools: `pathway_kpi` for the ATS (today and the day before the month, for the month's readmissions and executed actions) and per ASST, `compliance_by_step`, and `wait_by_hospital` over the month's 30 days for the pathway's step with a wait threshold. A template, filled by code in Italian and English, is the report: 30-day readmissions from day 0 with the pathway's reference, the month's readmissions, the rate per ASST, the on-track share and overdue steps, deadlines met per step, the wait per facility, and the agents' actions. The row goes to `reports` (`report_id` `rep_<run>_<n>`, `day`, `month`, `from_day`, `pathway_id`, `figures` with every number, `text` `{"it", "en"}`, `wording`, `evidence` the tools' sources). For the reports the cache manifest lists (`report_days`, D17) the engine asks `qwen3:30b-instruct` to rewrite the Italian as 4–5 sentences in the PNE style (`reporter-v1`) and `qwen3:4b-instruct` to translate it with facility names as placeholders; the text is used when both have only the template's numbers and keep the same facility names, else the template stands. `wording` says which, and the cache check (§8) fails on a template where the manifest lists the model's.

The baseline arm skips steps 6, 7 and 8.

**Intervention** (C32, `src/agents/intervention.py`, step 2.13), rules only. *Escalation ladder* (the pathway's `escalation`, §4) for every open problem: a flag rule that holds, or a step with a service or a telemonitoring start that is overdue and not booked for a coming day. When it opens, a reminder, or at once a call for a high-risk patient when `high_risk_skips_reminder`; still open `call_after_days` later, a `call_task`; still open `mmg_after_days` later, the patient joins one `notify_mmg` proposal a day (a new one only when none is waiting). *Warning sign*: a step rule that starts to hold gets a `call_task` that day. *Wait alarm* (D53): only while Monitoring has a regional wait alarm open, one `reschedule` a day for the facility (a new one only when none is waiting) moving its patients booked more than 14 days ahead to the hospital with the most free slots in 21 days (`free_slots`), as many as it has. Reminders are one action a day per kind of problem, listing the patients; calls are one action per patient. `payload` names the problem (`rule` or `step` id) and the `effect` the simulator gives it: `collect` (a no-dispense flag rule), `book` (a step with a service), `start` (telemonitoring), `review` (a warning sign); an action on a scope lists `payload.patients`, as ids sharing the effect or as objects with their own. A patient action's `evidence` is Monitoring's rule or deadline, `{"rule" or "step": id, run_id, day}`, since no tool answers for one patient; a reschedule's is the `wait_by_hospital` and `free_slots` sources. `escalation_step` is the highest rung reached by an open problem: 1 reminder, 2 call, 3 MMG notified. The stream carries at most 10 `action` messages a tick, proposals first, then calls by risk; `GET /actions` has every one.

*Capacity* (C34, step 2.27, D45): the engine hands the agents arm and its lever run the scenario's proposed lever (`whatif.proposed_lever`: the smallest of +1 to +4 slots a day at the first wait alarm's facility whose 6-month mean wait in the what-if grid is within the step's `max_wait_days`; +2 in scenario 1, +1 in 2 and 3). On the first day that facility's wait alarm is open, Intervention creates one `capacity_proposal` per run, `scope` `{"facility_id"}`, `payload` `{"facility_id", "service", "extra_slots", "slots_per_day", "from_day", "lever_run", "wait_days", "wait_days_without", "months", "wording"}`, `evidence` the alarm's `wait_by_hospital` source and `{"whatif": lever_run, "levers", "months", "run_id", "day"}`. Its level is fixed at 1, so it always waits; approved, it is executed and changes nothing in the run (no event: no agent changes capacity, CLAUDE.md rule 3), and the demo marks the lever run `approved` (§10). The rationale is a template filled by code; the demo shows `qwen3:30b-instruct`'s two sentences (`capacity-proposal-v1`) and `qwen3:4b-instruct`'s translation from the cache (D17, listed in the manifest) when both name the facility and every number in them is one of the facts code gave (`verifier.unsupported`), the template otherwise; `wording` says which (`model`, `template`), and the cache check (§8) fails on a `template` where the manifest lists the model's. The what-if grid stores no action counts, so the proposal leaves it unchanged.

**Speed:** ×1 = 1 simulated day per 2 s, ×4 = 2 days per s; operator controls pause, ×1, ×4, and jump to a day. C41: at ×1 the clock stops by itself on the day a wait alarm opens on the scenario on screen (the agents arm's regional alarm with a facility), so the demo stands on the day its cached answers were prepared for (scenario 2's day 33, scenario 3's day 29); at ×4 it goes on. A reset (`POST /sim/reset`) opens on the first scenario of D44's order again. Jump forward continues from the current day; jump backward replays deterministically from day 0 up to the target day (C9).

**Performance budgets** (C9, delivery plan D22). AC2 measures one run; the demo needs more:

| Budget | Value | Why |
|---|---|---|
| Live tick at ×4 | both arms of the scenario on screen together under 500 ms per simulated day | ×4 = 2 days per s |
| Start replay | all runs to day 23 in under 3 min: 6, or 9 with the lever runs (C28; 68 s measured) | runbook, T−5 min |
| What-if (AC4) | the result of 6 months, with and without agents, under 10 s; read from the precomputed grid (C27) | a full run takes minutes for 6 months |

The runs share nothing they write, so the two runs on screen advance in parallel threads, and the start replays all six in parallel (step 2.3: with Risk, one after the other took a p95 of 509 ms, in parallel 369–419 ms). Run databases checkpoint only when closed, because a checkpoint every 16 MB of WAL stalled ticks (p95 up to 760 ms); with that and the 0.001 rule for risk scores, both arms took a p95 of 280–417 ms on a laptop whose speed varies by about ±40% (step 2.7). **What-if** (C27, `src/engine/whatif.py`, step 2.5). The levers' results are full runs, the demo's own code, computed in advance by `uv run python -m engine.whatif` into `demo/whatif/scenario_<n>.json` and read back (D48, the fallback of D22 as the design). Per scenario: the baseline arm, the agents arm, and the agents arm with 1 to 4 extra slots a day for the service of the first wait alarm (§5.3), at its facility, from the day after the alarm, for 6 months (183 days, the last included); run ids `s<n>_agents_<service>+<k>`. A lever is a capacity change on top of the scenario (`sim.step.CapacityChange`, step 2.26), so a lever run is the agents run day by day until the lever starts. For each run the file keeps the readmissions from the lever's first day to the last (`kpi_daily.readmissions_30d` at the last day minus the day before the lever), the 30-day rate, on-track share and overdue patients on the last day, the mean wait per facility over the 6 months (`wait_by_hospital`, so the number the agents see), and the daily ATS KPIs. The grid is computed again after a change to the simulator, the engine or the agents, like the LLM cache; a test compares its baseline arm with the fixture run. A lever on the telemonitoring deadline changes only when agents act and comes with Intervention (step 2.13). **PNE forecast** (C35, `src/engine/pne.py`, step 2.6): after the 6 months every run goes on to day 364, the year's last day, and the file keeps its `year_end` `{day, readmissions_30d, readmission_rate_30d}` from `kpi_daily` (§5.2: from day 0, the PNE year); `pne.forecast` gives the three arms' year-end values for a lever and the pathway's `readmission_reference`. It is the simulation's own future with the same seed, run with the default autonomy levels, not a fitted trend; there is no ATS target in the data, so the reference is the published rate.

**Feedback hook:** `sim.feedback.apply(run_id, actions_executed_today) -> DataFrame of events` (§3.1 columns). The action service calls it once a day, after the simulator's step for that day, with the §7.1 rows it executed (`action_id`, `type`, `patient_id`, `executed_day` required; one day per call). The returned events record the actions themselves on day D (`call_task` → `CALL`, `reminder` → `REMINDER`, with `source = agent_action` and the `action_id`); their effects appear from day D + 1 in the simulator's own events. The process running a run registers its simulator with `sim.feedback.register(run_id, sim)`. Until step 2.13 the effects are a no-op except Maria's scripted response (step 1.19). The probabilities of each effect (for example, how much a call raises dispensing) will be configuration, listed in the limitations.

## 10. API and WebSocket

REST, FastAPI, JSON. **Every path below is under the `/api` prefix** (for example `GET /api/health`, `WS /api/stream`); everything else is the built console, served by FastAPI from `src/ui/dist` (D13). `run` defaults to the scenario on screen and the `agents` arm. The API starts the demo's runs itself (six, or nine with the lever runs, C28) and answers 503 on data and control paths until they stand on the start day (about 30–70 s on the team laptops). Control paths return `{"scenario", "day", "speed"}` (C17).

| Method and path (under `/api`) | Purpose |
|---|---|
| `GET /health` | liveness |
| `POST /sim/start`, `/sim/pause`, `/sim/reset` | start the scenario on screen (×1, or the last speed), pause it, rebuild all runs to the start day paused (C17) |
| `POST /sim/speed` `{factor}` | 0 (pause), 1, 4 |
| `POST /sim/scenario/{n}` | change the scenario on screen (the demo bar, C37); it stays paused until the operator starts it |
| `GET /sim/cache`, `PUT /sim/cache` `{mode}` | C37: the LLM gateway's mode for the demo bar's indicator (the team only): `{"mode"}`; `PUT` takes `cache_only` (the default, D14) or `cache_first`; `live` is for warm-ups only, 422 |
| `POST /sim/jump/{day}` | jump to a day |
| `GET /kpi?run&pathway_id&level&key` | `kpi_daily` rows |
| `GET /capacity?service&run&pathway_id&day` | C28: per facility of `service`, over the 7 days up to `day` (the run's last day by default): `{day, facility_id, name, slots_total, slots_booked, use_pct, bookings, wait_mean, wait_median, wait_p90}`. Waits are booking to booked day of the pathway's patients; `wait_mean` is `wait_by_hospital` with `period_days = 7`, the alarm's number; median and p90 are exact (integer days) |
| `GET /sankey?run&pathway_id` | `sankey_flows` |
| `GET /map?run&pathway_id` | `map_comuni` rows; regional alarms arrive on the stream (C18) |
| `GET /worklist?run&day` | `worklist_today` of `day`, or of the latest day, without the `day` column, by `rank` (C20); C37: with the patient's `age`, `lives_alone` and `comune_name` for the Centro Servizi |
| `GET /patients/{id}?run&day` | Paziente 360: timeline of events and actions, state per pathway (shape below, C15). With `day`, a recording from `demo/story/` (C17): only `p_00001`, `s2_baseline`, day 62 exists; anything else is 404 |
| `GET /actions?run&status&day` | action queue and feed; C38: with `day`, the actions created or executed that day (Attività agenti after a jump) |
| `GET /investigations?run` | the run's `investigations` rows (§6, C24), the latest first, JSON columns parsed (C25) |
| `GET /reports?run` | C36: the run's `reports` rows, the latest first: `{report_id, day, month, from_day, pathway_id, figures, text: {"it", "en"}, wording, evidence}` |
| `GET /pathways/{pathway_id}` | the pathway file of §4 as it is, so the console names steps and drugs from data (C22); 404 for an unknown id. Needs no run. `spec/pathways/<pathway_id>.json` is its fixture |
| `POST /actions/{id}/approve`, `/reject`, `/undo` | decisions, on the agents arm of the scenario on screen; C42: on the action's own run, read from its id (a bed in a baseline run), with actor `doctor` for a `bed_assignment`. C30: approve and reject take an action in `proposed` and return `{action_id, status}`; 404 for an unknown action, 422 for one already decided. The audit log gets `approved` or `rejected` with actor `manager` (the demo has no login). C31: approve executes the action at once (`status` `executed`), `/undo` takes an executed action (`undone`, otherwise 422), and each pushes the changed action as an `action` message |
| `GET /settings`, `PUT /settings/autonomy` | autonomy per action type. C30: `GET` returns `{"autonomy": {type: {level, default, fixed}}}` for the types of §7.2, from the defaults and the `config_changed` entries of the audit log (`details`: `{setting: "autonomy", type, level, before}`); `PUT {type, level}` holds for the ATS, so it is logged in every agents run of the demo, and answers like `GET`; 422 for an unknown type, a level outside 0–3 or `rule_proposal` other than 1. A run built again after a jump back starts from the defaults |
| `GET /questions` | C40: the questions Chiedi suggests for the scenario on screen, the cache manifest's (§8), with the day they are prepared for: `{scenario, day, questions}`; the console holds none of its own (AC17) |
| `POST /ask` `{question}` | C29: the Investigator answers on the agents arm of the scenario on screen, on its day; returns the stored `investigations` row, its steps arrive on the WebSocket. In the demo the answer comes from the cache (D14): a question nobody warmed gets 503 "no answer", and no template stands in (Solution Plan §8). `question` 3–500 characters |
| `POST /pathways` `{pdta_text}` | Pathway Builder (option B, delivery plan D23) |
| `POST /whatif` `{levers: {extra_slots}, months}` | what-if with and without agents for the scenario on screen, from its grid (C27): `{scenario, facility_id, facility, service, lever_day, last_day, months, base_slots, levers, baseline, agents, lever, avoided_readmissions, precomputed: true}`, where `baseline`, `agents` and `lever` are run summaries `{run_id, readmissions, readmission_rate_30d, on_track_pct, overdue, wait_days, wait_by_facility}` and `avoided_readmissions` is baseline minus lever. `extra_slots` 0–4, `months` 6; anything else 422, no grid 503. It does not wait for the runs. C35: also `pne` `{day, baseline, agents, lever, reference}`, the PNE forecast to year end (§5.2): each arm's `{readmissions_30d, readmission_rate_30d}` on `day` 364, and the pathway's `readmission_reference` (C23) or null. C39: with a `readmission_cost`, also `saving_eur` (`avoided_readmissions` × its `eur`) and `cost` |
| `POST /admissions` `{patient_id, run?, day?, diagnosis?, facility_id?, choice?}` | Bed Finder (C42, demo step 9c): in `run` (the agents arm on screen by default) on `day` (the run's today by default, not later). Without `diagnosis` and `facility_id` (the emergency department), the patient's `ADMISSION` of that day in the run gives them, as Maria's of day 47 without CarePath. Returns `{admission: {run_id, patient_id, day, facility_id}, candidates, action}` (shapes in §7.2; `action` null when no ward has a bed free today) and pushes the action as an `action` message. 404 for a run of no scenario; 422 for an unknown patient, a day after today, no admission and no diagnosis, a diagnosis without a ward, or a `choice` without a bed free today |
| `GET /reveal/{scenario}` | Rivelazione only; reads `scenario_truth`. C37: `{scenario, bottleneck, mmg_group, rural_comuni}`, each `{found, hidden, match}`. `found` comes from the agents arm's own regional alarms (§5.3), null before they open: the first wait alarm's `{day, facility, asst_id}`; the group alarm on `adherence_by_group` `{day, group, text}`; the one on `adherence_by_area` `{day, text}`. `hidden` is the truth: `{facility, asst_id}`, `{group}`, `{comuni, named}` (`named`: the hidden comuni the alarm's text names). `match`: the same facility, the same group, at least half of the comuni named. 404 for a scenario not in the demo |
| `WS /stream` | live messages |

**WebSocket envelope** (already implemented in `src/api/main.py`, typed for the console in `src/ui/src/lib/stream.ts`):

```json
{"type": "tick", "scenario": 2, "day": 35, "payload": {}}
```

| `type` | `payload` |
|---|---|
| `tick` | `{"speed": 4, "kpi": {...}}`: headline numbers for the cards; with a lever run (C28) also `"lever_run": {"run_id", "day", "approved"}`, its day behind the tick's while it catches up, and `approved` true once the manager approved the scenario's `capacity_proposal`, until a jump back or a reset rebuilds the runs (C34). Approving one also pushes a `tick` |
| `alert` | `{"alert_id": "al_s2_agents_338", "level": "patient" \| "regional", "text": {"it": "...", "en": "..."}, "facility_id": "osp_B", "group_key": null, "investigation_id": "..."}`; `group_key` names the group of a group alarm (C26), and `alert_id` links the investigation to its alarm |
| `action` | one row of `actions` |
| `investigation` | `{"investigation_id", "step": n, "tool", "args", "result_summary": {"it", "en"}, "verified": true \| false \| null, "final": false}`; `verified` is true when the Verifier passed every claim of the step, false when one has an issue, null without a checked claim (C33) |
| `report` | C36: `{"report_id", "month", "from_day", "title": {"it", "en"}, "wording": "model" \| "template"}`, on the last day of a month; the text is in `GET /reports` |

**Tick `kpi`** (C15): the `ats` row of `kpi_daily` for the pathway on screen and the tick's day, without `day`, `level` and `key`.

**Paziente 360** (C15), `GET /patients/{id}?run`. The console calls it once per arm for the with/without toggle:

```json
{
  "patient": {"patient_id": "p_00001", "...": "every patients column", "comune_name": "Poggio Rusco"},
  "pathways": [{"...": "the patient's pathway_state rows"}],
  "timeline": [
    {"day": 31, "kind": "action", "action_id": "act_s2_agents_1", "type": "call_task", "agent": "intervention",
     "status": "executed", "rationale": {"it": "...", "en": "..."}},
    {"day": 31, "kind": "event", "event_id": "ev_2345", "event_type": "CALL", "code": "delivery_arranged", "value": null,
     "facility_id": null, "facility_name": null, "source": "agent_action", "action_id": "act_s2_agents_1"}
  ]
}
```

The timeline holds every event of the patient, warm-up history included, and every action on the patient (on its `created_day`). It is sorted by day; within a day, actions come before events and events keep their order.

## 11. Acceptance criteria

Every criterion has a test in `testing/`; acceptance tests carry `@pytest.mark.acceptance`.

| AC | Criterion | Measured by | Test | Layer | Owner |
|---|---|---|---|---|---|
| AC1 | Agents find patterns 1–3 without hints in the prompt | agent log vs `scenario_truth` | `test_ac01_patterns_found.py` | core | R3 |
| AC2 | One simulated day for all patients under 1 s | timer | `test_ac02_tick_speed.py` | core | R2 |
| AC3 | KPI, Sankey and map under 200 ms | timer | `test_ac03_views_speed.py` | core | R2 |
| AC4 | What-if 6 months, with and without agents, under 10 s (read from the precomputed grid of full runs, delivery plan D48) | timer | `test_ac04_whatif_speed.py` | core | R2 |
| AC5 | Investigator under 2 s from cache (live 30 s not reachable on CPU laptops, delivery plan D18) | timer | `test_ac05_investigator_speed.py` | core | R3 |
| AC6 | Ask correct on at least 8 of 10 benchmark questions, measured on the questions Chiedi shows in the demo (scenario 2: q01, q08–q10; at least 80% right; day 35 of the baseline arm, replayed from the cache; `testing/benchmark/run.py`) | expected answers | `test_ac06_benchmark.py` | core | R3 |
| AC7 | No action above its autonomy level without approval | test + audit log | `test_ac07_autonomy.py` | core | R3 |
| AC8 | Fewer readmissions with agents than without, same seed | simulation report | `test_ac08_effect.py` | core | R1 |
| AC9 | 10 consecutive full demo runs without a stop | rehearsal and cache log, kept by hand in `demo/rehearsals.md` | `test_ac09_rehearsals.py` | core | R5 |
| AC10 | Verifier catches all injected wrong numbers in 5 answers, no false alarms | injected errors | `test_ac10_verifier.py` | optional | R3 |
| AC11 | Rule Advisor proposes a rule for pattern 2; once approved it raises alarms the next day | rule and alarm log | `test_ac11_rule_advisor.py` | optional | R3 |
| AC12 | Daily list under 30 s; at least 15 of the top 20 high-risk or overdue | timer + truth | `test_ac12_worklist.py` | optional | R2 |
| AC13 | In each of the 3 scenarios agents name the right ASST, comune group and MMG group | 3 runs vs `scenario_truth` | `test_ac13_scenarios.py` | core | R1 |
| AC14 | Maria's trajectory is identical on every run (readmitted on day 47 without agents, intervention on day 31 with) | simulation log | `test_ac14_maria.py` | core | R1 |
| AC15 | Enrollment Advisor finds at least 90% of pattern-5 candidates and enrolls them, with MMG notice and audit entry | truth + audit | `test_ac15_enrollment.py` | option B | R2 |
| AC16 | New pathway from approval to compliance under 60 s | timer | `test_ac16_new_pathway.py` | option B | R2 |
| AC17 | Same tools, KPIs and console work for both pathways without code changes | test with two pathway models | `test_ac17_generic.py` | core | R2 |
| AC18 | Bed Finder answers under 3 s; ward matches diagnosis; bed really free | 20 test admissions | `test_ac18_bed_finder.py` | optional | R2 |
| AC19 | Confirm mode writes no admission without confirmation; assign mode logs every admission and can undo it | test + audit log | `test_ac19_bed_modes.py` | optional | R3 |

## 12. Open questions for the spec review

| # | Question | Who answers | Needed by |
|---|---|---|---|
| Q1 | Exact ICD-9-CM, ATC and LOINC codes for HF and T2D. **Closed** (D28): demo values, no clinical confirmation for the PoC | Italian colleague via R5 | week 2, day 1 |
| Q2 | Cost per readmission in EUR and its public source. **In part answered** (D61, 2 Nov 2026): the demo uses 3,500 euros, a value the lead chose, labelled as assumed; the public source is still open | R5 | week 2 |
| Q3 | Changes C1–C11: accepted as proposed? **Accepted**: C1–C10 by the TL review, C11 with step 1.15 (both 28 Oct 2026). C12 and C13 accepted with D29 and D31 (28 Oct 2026). C14–C21 proposed with D32–D39 (28 Oct 2026) | all, at the sync | week 1 |
| Q4 | Dropped threshold: 30 days overdue, or 2 steps overdue at once, right for HF? | R5 with the Italian colleague | week 2 |
| Q5 | Daily limit of automatic actions per facility: 50 a sensible default? | R3, R5 | week 2 |
| Q6 | Do we need calendar dates on screen, or is "Giorno N" enough for the audience? | R5 | week 2 |
| Q7 | `map_comuni`: what `adherence_pct` measures and when `alarm` is true (**answered by C18**, step 2.2); `worklist_today`: the type of `pathways` and the values of `outcome` (**answered by C20**, step 2.4) | R2, R4 | closed |
