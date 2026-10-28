# CarePath AI — SPEC

| | |
|---|---|
| Status | **DRAFT v0.2**, for review at the week-1 sync. Freezes as tag `spec-v1` at the end of week 2, day 2 (delivery plan, step 1.9) |
| Last updated | 28 Oct 2026 |
| Owner | R5. Every section has a co-owner who signs it off (§0) |
| Sources | [Solution Plan](../docs/CarePath-AI-Solution-Plan.pdf) §6–§9 and §13; [Delivery Plan](../docs/DELIVERY_PLAN.md) |
| Rule | Nobody builds against anything that is not in this file. Whoever waits on another role works with fixtures of the same shape (`testing/fixtures/`) |

## 0. Sign-off and change control

| Section | Co-owner | Signed off |
|---|---|---|
| §2 Conventions, §3 Data | R1 | ☐ |
| §4 Pathway model | R2 | ☐ |
| §5 State and views | R2, R4 | ☐ |
| §6 Tools | R3 | ☐ |
| §7 Actions and autonomy | R3 | ☐ |
| §8 LLM gateway | R3 | ☐ |
| §9 Simulation runtime | R1, R2 | ☐ |
| §10 API and WebSocket | R4 | ☐ |
| §11 Acceptance criteria | all | ☐ |

After `spec-v1`, a change needs: agreement at a sync, an entry in the decision register (delivery plan §11), a version bump at the top of this file, and updated fixtures in the same commit (delivery plan, D20).

### Changes vs Solution Plan (proposed in this draft, need agreement)

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
| C9 | Only the 2 runs of the scenario on screen advance after the envelope; jump forward continues from the current day; performance budgets beyond AC2 (§9) | Demo pacing and budgets, delivery plan D21 and D22 |
| C11 | Days before 0 are history: the simulator warms up for 120 days (−120..−1) and keeps those events (§2) | Rules and tools look back 30–180 days; without history, `no_dispense('C03CA01', 30)` would fire for every patient on day 30 |
| C10 | Cache completeness check (§8) | Any change to the simulator, engine, tools or prompts after the warm-up can change cache keys; the check finds misses before a rehearsal does |

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
| Language | Data and code in English; every user-facing string in Italian (UI, reports, call scripts, rationales) |
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

**`beds`** (optional layer): `facility_id`, `ward` (`cardiologia`, `medicina_interna`, `endocrinologia`), `beds_total`.
**`bed_occupancy`** (C4, optional layer): `day`, `facility_id`, `ward`, `occupied`, `expected_discharges_next_2d`.

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
  "eligibility": {"any_diagnosis": ["428.*"], "any_drug_atc": ["C03CA01"]},
  "status_thresholds": {"due_soon_days": 7, "dropped_after_days": 30, "dropped_if_overdue_steps": 2},
  "steps": [
    {"id": "discharge", "event": "DISCHARGE", "codes": ["428.*"]},
    {"id": "telemon", "event": "TELEMON_START", "due_days": 7, "after": "discharge"},
    {"id": "cardio_visit", "event": "VISIT", "specialty": "cardiologia", "due_days": 30, "after": "discharge"},
    {"id": "echo", "event": "IMAGING", "codes": ["88.72"], "due_days": 90, "after": "discharge"},
    {"id": "lab_bnp", "event": "LAB", "loinc": ["30934-4"], "every_days": 90}
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

### 5.2 Views

All views are DuckDB views or tables refreshed once per tick and must answer in under 200 ms (AC3).

| View | Grain | Columns |
|---|---|---|
| `kpi_daily` | day × pathway × level (`ats`, `asst`, `comune`) × key | `patients`, `on_track_pct`, `overdue`, `dropped`, `readmissions_30d`, `readmission_rate_30d`, `actions_executed`, `actions_pending`, `est_readmission_cost_eur` |
| `sankey_flows` | pathway × from_step × to_step × status | `patients` |
| `map_comuni` | comune × pathway | `adherence_pct`, `risk_mean`, `high_risk_patients`, `readmission_rate_30d`, `alarm` |
| `worklist_today` | patient (all pathways merged) | `rank`, `risk_score`, `reasons` (Italian), `pathways`, `escalation_step`, `script` (filled by Daily Worklist), `outcome` (filled by the operator or the simulation) |

**Readmission, PNE-style:** an unplanned `ADMISSION` within 30 days after a `DISCHARGE` with an HF main diagnosis. Rate = such readmissions ÷ HF discharges in the period. Simplified versus the official PNE protocol; the simplification is listed in the limitations.

**Cost:** `est_readmission_cost_eur = readmissions × readmission_cost_eur`, a single configured parameter. Its value and source (e.g. the DRG tariff) are open question Q2.

## 6. Tools

All tools are **read-only**, take typed arguments and return JSON. The Investigator uses only these tools and never writes SQL (Solution Plan §8 guardrails). Tool descriptions shown to the model are in Italian; names and arguments are in English.

Every tool gets its database from `engine.db.connect_for_tools(run_id)` and from nothing else: the run database read-only, with DuckDB's access to files disabled and the configuration locked. A tool therefore cannot read `demo/truth/` or the scenario files, attach another database, or write. Agent code does not import the simulator (step 1.18, tested).

Every result has the same envelope (C5):

```json
{
  "data": {"Ospedale A": 22, "Ospedale B": 41, "Ospedale C": 14},
  "source": {"tool": "wait_by_hospital", "args": {"pathway_id": "hf_lombardia_v1", "step": "echo", "period_days": 90}, "run_id": "s2_agents", "day": 35}
}
```

Errors: `{"error": {"code": "unknown_step", "message": "…"}}`. Codes: `unknown_pathway`, `unknown_step`, `bad_argument`, `empty_result`.

Every number in `data` follows the precision rule in §2. `testing/test_tools_deterministic.py` calls every tool on two fresh connections with default threads, on a full-size run (10,000 patients, 365 days), and asserts identical bytes (C7).

| Tool | Arguments | `data` |
|---|---|---|
| `compliance_by_step` | `pathway_id`, `asst?` | `{step: on_time_fraction}` |
| `wait_by_hospital` | `pathway_id`, `step`, `period_days=90` | `{facility_name: mean_wait_days}` |
| `patients_overdue` | `pathway_id`, `step`, `asst?`, `limit=20` | `{count, patients: [{patient_id, days_overdue, risk_score}]}` |
| `free_slots` | `service`, `asst?`, `horizon_days=21` | `{facility_name: free_slots}` |
| `adherence_by_group` | `pathway_id`, `grouping` (`mmg`, `mmg_group`, `comune`, `age_band`), `measure` (`dispensing`, `telemonitoring`; default `dispensing`, C8), `period_days=60` | `{group: fraction}`, plus `rest_of_ats` |
| `readmissions_by_comune` | `pathway_id`, `period_days=180` | `{comune_name: rate}`, sorted descending |
| `risk_drivers` | `pathway_id`, `segment?` | `{drivers: [{name, weight}]}` |
| `compare_segments` | `pathway_id`, `a`, `b` (segments), `metric` | `{a: value, b: value, difference}` |

**Measures and metrics (C8):**

- `dispensing`: share of patients who collected each chronic drug of the pathway within the period.
- `telemonitoring`: share of patients with telemonitoring active who sent at least one reading in the last 7 days of the period.
- `metric` for `compare_segments` is one of `dispensing`, `telemonitoring`, `readmission_rate_30d`, `on_time_fraction`, `risk_mean`.

**Segment (C8):** a JSON object with any of `asst_id`, `comune_istat` (list), `coop_id`, `age_min`, `age_max`, `lives_alone`, `distance_km_min`. All keys are optional and combine with AND; `{}` is the whole population of the pathway. Example for pattern 3: `{"lives_alone": true, "distance_km_min": 40, "age_min": 75}`.
| `eligibility_candidates` | `pathway_id`, `mmg?` | `{count, patients: [{patient_id, reasons}]}` |
| `free_beds` (optional) | `diagnosis`, `asst?` | `[{facility_id, ward, free_now, free_in_2d, distance_km}]` |

The canonical JSON schemas for these tools live in `src/agents/tools.py` and are the single source for both the agents and the LLM evaluation (`testing/llm_eval.py` will import them once they exist).

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
| `rationale_it` | VARCHAR | Italian text for the UI |
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
| `bed_assignment` | Bed Finder | 3 (alternative mode: 2 with doctor confirmation) | — |

### 7.3 Action service

The only component that writes state (delivery plan, principle 4). For every action it checks, in order:

1. **Guardrails that cannot be switched off:** no therapy change, no diagnosis, no decision on *whether* a patient needs an exam or an admission (only *where* and *when*).
2. **Autonomy level** for the type: below 3 the action waits in the approval queue.
3. **Daily limit** of automatic actions per facility (configurable, default 50).
4. **Evidence present:** an action without at least one tool `source` is rejected.

It then executes the action, writes the audit log, emits the effect as events for day D+1 through the simulator feedback hook (§9), and pushes an `action` message on the WebSocket. `undo` on an executed action writes a compensating event and sets the status to `undone`.

**Audit log** (`audit_log`): `ts_day`, `action_id`, `event` (`created`, `approved`, `rejected`, `executed`, `undone`, `config_changed`), `actor`, `details` JSON. Every configuration change (autonomy, rules, pathways) is logged with its author.

## 8. LLM gateway

One function used by every agent (delivery plan, step 2.7):

```python
complete(agent: str, prompt_version: str, messages: list, *, tools=None, schema=None, model: str) -> GatewayResult
```

| Rule | Value |
|---|---|
| Sampling | temperature 0, fixed seed |
| Output | JSON schema enforced through Ollama structured output whenever `schema` is given; validated after the call |
| Retry | 1 retry on invalid output |
| Timeout | 20 s, then fall back to the cache; 600 s in warm-up runs that fill the cache |
| Models | `qwen3:30b-instruct` for cached outputs, `qwen3:4b-instruct` for short live text (delivery plan, D11); `keep_alive` keeps the model in use loaded |
| Cache scope | only outputs the demo script shows, listed in `demo/cache/manifest.json`; everything else uses the agent's template (delivery plan, D17) |
| Cache key | SHA-256 of `(agent, model, prompt_version, canonical JSON of messages, tools, schema)`. Canonical JSON: keys sorted, no whitespace, UTF-8, numbers as tools return them after rounding (§2) |
| Cache completeness (C10) | `testing/test_cache_complete.py` (marker `demo`) plays the demo script through the API in `cache_only` mode and fails on any cache miss. It runs after every change to the simulator, engine, tools or prompts once a cache exists, and before every rehearsal. A miss is fixed by warming the listed entries again in `live` mode. The Investigator has no template fallback (Solution Plan §8), so this check is its guard |
| Cache store | `demo/cache/<agent>/<key>.json` |
| Modes | `live` (call, then cache; used for warm-up), `cache_first` (development and rehearsals), `cache_only` (default at demo start, D14; the operator hotkey toggles it) |
| Log | one line per call in `logs/llm.jsonl`: `ts`, `agent`, `model`, `prompt_version`, `key`, `mode`, `cache_hit`, `latency_ms`, `valid`, `retries` |

**Thinking models:** the gateway always sends `think: false`. Models that cannot turn thinking off (for example the plain `qwen3:4b` and `qwen3:30b` tags) are not allowed; use the `-instruct` tags.

## 9. Simulation runtime

**Run:** `run_id = s<scenario>_<arm>[_<lever-hash>]`, for example `s2_agents`, `s2_baseline`, `s2_agents_echo+1`. A run is one simulator instance with its own seed stream and its own DuckDB file. Demo start launches six runs, 3 scenarios × 2 arms, replays them to the start day (day 23) and pauses (delivery plan, D21). After the envelope is chosen, only the 2 runs of the scenario on screen advance; the other 4 stay paused (C9). The screen shows one scenario; the arm switch drives Confronto and "Senza CarePath".

**Tick order for day D** (Solution Plan §9):

1. The simulator emits events for day D, including the effects of actions executed on day D−1.
2. The state engine updates `pathway_state` for patients with new events and sweeps deadlines for all.
3. Risk rescores patients with new events.
4. Monitoring applies pathway rules and approved Rule Advisor rules; raises patient deviations and regional alarms.
5. Views refresh.
6. Intervention handles new deviations through the action service; Daily Worklist builds the list at the start of the day.
7. On a regional alarm, the Investigator starts asynchronously; the Verifier checks its answer.
8. The WebSocket pushes the new state, alarms and actions.

The baseline arm skips steps 6 and 7.

**Speed:** ×1 = 1 simulated day per 2 s, ×4 = 2 days per s; operator controls pause, ×1, ×4, and jump to a day. Jump forward continues from the current day; jump backward replays deterministically from day 0 up to the target day (C9).

**Performance budgets** (C9, delivery plan D22). AC2 measures one run; the demo needs more:

| Budget | Value | Why |
|---|---|---|
| Live tick at ×4 | both arms of the scenario on screen together under 500 ms per simulated day | ×4 = 2 days per s |
| Start replay | all 6 runs to day 23 in under 3 min | runbook, T−5 min |
| What-if (AC4) | 2 arms × 182 days under 10 s: about 27 ms per arm-day if the arms run one after the other, 55 ms if they run in parallel processes | 20–35 times stricter than AC2 |

What-if runs skip LLM calls, view refreshes and WebSocket pushes; they compute KPIs once at the end. If AC4 is missed at the week-3 checkpoint, the demo lever's results are precomputed per scenario and replayed (D22).

**Feedback hook:** `sim.feedback.apply(run_id, actions_executed_today) -> list[event]`. The probabilities of each effect (for example, how much a call raises dispensing) are configuration, listed in the limitations.

## 10. API and WebSocket

REST, FastAPI, JSON. **Every path below is under the `/api` prefix** (for example `GET /api/health`, `WS /api/stream`); everything else is the built console, served by FastAPI from `src/ui/dist` (D13). `run` defaults to the scenario on screen and the `agents` arm.

| Method and path (under `/api`) | Purpose |
|---|---|
| `GET /health` | liveness |
| `POST /sim/start`, `/sim/pause`, `/sim/reset` | control all runs |
| `POST /sim/speed` `{factor}` | 0 (pause), 1, 4 |
| `POST /sim/scenario/{n}` | change the scenario on screen (the envelope hotkey) |
| `POST /sim/jump/{day}` | jump to a day |
| `GET /kpi?run&pathway_id&level&key` | `kpi_daily` rows |
| `GET /sankey?run&pathway_id` | `sankey_flows` |
| `GET /map?run&pathway_id` | `map_comuni` + alarms |
| `GET /worklist?run&day` | `worklist_today` |
| `GET /patients/{id}?run` | Paziente 360: timeline of events and actions, state per pathway |
| `GET /actions?run&status` | action queue and feed |
| `POST /actions/{id}/approve`, `/reject`, `/undo` | decisions |
| `GET /settings`, `PUT /settings/autonomy` | autonomy per action type |
| `POST /ask` `{question}` | starts an investigation; steps arrive on the WebSocket |
| `POST /pathways` `{pdta_text}` | Pathway Builder (option B, delivery plan D23) |
| `POST /whatif` `{levers, months}` | what-if with and without agents |
| `POST /admissions` `{patient_id, diagnosis}` | Bed Finder (optional) |
| `GET /reveal/{scenario}` | Rivelazione only; reads `scenario_truth` |
| `WS /stream` | live messages |

**WebSocket envelope** (already implemented in `src/api/main.py`, typed for the console in `src/ui/src/lib/stream.ts`):

```json
{"type": "tick", "scenario": 2, "day": 35, "payload": {}}
```

| `type` | `payload` |
|---|---|
| `tick` | `{"speed": 4, "kpi": {...}}`: headline numbers for the cards |
| `alert` | `{"level": "patient" \| "regional", "text_it": "...", "facility_id": "osp_B", "investigation_id": "..."}` |
| `action` | one row of `actions` |
| `investigation` | `{"investigation_id", "step": n, "tool", "args", "result_summary_it", "verified": true \| false \| null, "final": false}` |

## 11. Acceptance criteria

Every criterion has a test in `testing/`; acceptance tests carry `@pytest.mark.acceptance`.

| AC | Criterion | Measured by | Test | Layer | Owner |
|---|---|---|---|---|---|
| AC1 | Agents find patterns 1–3 without hints in the prompt | agent log vs `scenario_truth` | `test_ac01_patterns_found.py` | core | R3 |
| AC2 | One simulated day for all patients under 1 s | timer | `test_ac02_tick_speed.py` | core | R2 |
| AC3 | KPI, Sankey and map under 200 ms | timer | `test_ac03_views_speed.py` | core | R2 |
| AC4 | What-if 6 months, with and without agents, under 10 s | timer | `test_ac04_whatif_speed.py` | core | R2 |
| AC5 | Investigator under 2 s from cache (live 30 s not reachable on CPU laptops, delivery plan D18) | timer | `test_ac05_investigator_speed.py` | core | R3 |
| AC6 | Ask correct on at least 8 of 10 benchmark questions | expected answers | `test_ac06_benchmark.py` | core | R3 |
| AC7 | No action above its autonomy level without approval | test + audit log | `test_ac07_autonomy.py` | core | R3 |
| AC8 | Fewer readmissions with agents than without, same seed | simulation report | `test_ac08_effect.py` | core | R1 |
| AC9 | 10 consecutive full demo runs without a stop | rehearsal and cache log | manual, `demo/rehearsals.md` | core | R5 |
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
| Q2 | Cost per readmission in EUR and its public source | R5 | week 2 |
| Q3 | Changes C1–C10: accepted as proposed? **Accepted** (TL review, 28 Oct 2026) | all, at the sync | week 1 |
| Q4 | Dropped threshold: 30 days overdue, or 2 steps overdue at once, right for HF? | R5 with the Italian colleague | week 2 |
| Q5 | Daily limit of automatic actions per facility: 50 a sensible default? | R3, R5 | week 2 |
| Q6 | Do we need calendar dates on screen, or is "Giorno N" enough for the audience? | R5 | week 2 |
