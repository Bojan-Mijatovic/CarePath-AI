# CarePath AI — Delivery Plan by Phase

| | |
|---|---|
| Source of truth | [CarePath-AI-Solution-Plan.pdf](CarePath-AI-Solution-Plan.pdf) (22 Oct 2026). This plan turns it into executable steps; where they differ, the Solution Plan wins until the change is agreed at a sync and logged in the decision register (§11). |
| UI reference | [CarePath-AI-UI-demo-srpski.html](CarePath-AI-UI-demo-srpski.html), screens for demo steps 1–10 |
| Horizon | 4 workshop weeks: preparation, spec + simulator, one build week, stabilisation |
| Constraint | Zero cost and fully offline on the day of the demo |
| Last updated | 26 Oct 2026 |

## 1. Summary

We deliver a working PoC on 10,000 synthetic heart-failure patients, optionally plus about 3,000 with type 2 diabetes, and a live demo of about 7 minutes for an Italian audience. Everything runs locally on free, open-source software and free local models.

The plan has five phases. Each one ends with a gate, measured against the acceptance criteria (AC1–AC19) from the Solution Plan:

| Phase | When | Goal | Exit gate |
|---|---|---|---|
| 0. Foundations | Week 1 | Same environment for everyone, models chosen on numbers, repo skeleton running | Hello stack runs from a clean clone; model decision recorded |
| 1. Spec, contracts, simulator | Week 2 | Frozen contracts; simulator with 3 scenarios and Maria that provably contains the injected patterns | **Scope gate:** pattern notebook passes for all 3 scenarios, Maria trajectory stable (AC13 data side, AC14), SPEC approved |
| 2. Core build | Week 3, days 1–5 | Whole demo flow works end-to-end every day | Core ACs measurable: AC1–AC8, AC13, AC14, AC17 |
| 3. Gated extensions | Week 3, days 3–5 (parallel) | Optional agents, option B, Bed Finder, added in order and only if the core is healthy | Checkpoint on day 3 and AC10–AC12, AC15, AC16, AC18, AC19 |
| 4. Stabilisation and demo | Week 4 | 10 consecutive offline runs without a stop | AC9; runbook rehearsed on the main and the backup machine |

The biggest risk is unchanged from the Solution Plan: the simulator in week 2. The biggest new finding is that local models on our laptops are slow and occasionally wrong about facts (§3). So the design is **cache-first**: every LLM output that appears in the demo is generated before the demo and replayed. Live generation is a bonus, not a dependency.

## 2. Engineering principles

These apply to every phase. A pull request that breaks one of them needs a decision-register entry.

1. **Contracts before code.** Every interface between roles is in `spec/SPEC.md` before anyone builds against it. Whoever waits on another role works with fixtures of the same shape (`testing/fixtures/`).
2. **Code computes, the LLM phrases.** Numbers, names, dates and rankings come from code (rules, SQL views, XGBoost). The LLM only writes sentences around values it received from a tool or a template. It never produces a fact that a tool did not return.
3. **Cache-first LLM.** Seeds are fixed, so the inputs at every rehearsal are identical. Every LLM call goes through one gateway (§7.2, step 2.7), keyed by `(agent, model, prompt_version, input_hash)`. The cache is warmed ahead of time on the strongest machine available.
4. **One writer.** Agents only read, through tools. The action service is the only component that changes state, and only after the autonomy and guardrail checks. Every action is written to the audit log and can be undone.
5. **Disease is configuration.** Pathway JSON plus data, never `if pathway == "hf"` in code (AC17).
6. **Offline by default.** No CDN, no public APIs, no telemetry. Fonts, JS, GeoJSON, models and cache all live on disk. We test with the network switched off from week 3.
7. **Zero cost.** Only tools with permissive or free licences and no paid tier in the critical path (§10).
8. **End-to-end every day from week 3.** A feature that does not work in the full flow is not done.

## 3. Environment baseline (measured 26 Oct 2026)

| Item | State |
|---|---|
| Reference laptop (every team laptop, D12) | Intel i7-1355U (10 cores, 12 threads), 32 GB RAM, Intel Iris Xe, **no NVIDIA GPU** |
| Python | 3.12 via `uv`; `.venv` from `uv sync` (`pyproject.toml`, `uv.lock`) |
| Packages | numpy, pandas, duckdb, scikit-learn, xgboost, fastapi, uvicorn, pydantic, ollama; dev: pytest, jupyterlab |
| LLM runtime | Ollama 0.40.11, local server on `127.0.0.1:11434` |
| Models pulled | `qwen3:30b-instruct` (18 GB), `qwen3:4b-instruct` (2.5 GB); evaluated and not recommended: `nemotron-3.5-lightning:30b`, `qwen3:8b`, `qwen2.5:7b`, `qwen2.5:14b`, `mistral-nemo:12b` |
| Evaluation | `testing/llm_eval.py <model> [...]`; `--investigate-only` reruns just the investigation; results in `testing/results/` |

### 3.1 Model evaluation (step 0.4)

Seven free local models, CPU only, temperature 0, seed 42, thinking off. Three tests per model:

- **Italian:** 5 texts written from facts that code supplies (MMG note, alarm, call script, rule proposal, report line), checked automatically for missing and wrong facts, then read by a person.
- **Tools:** 5 questions with the 7 tools of Solution Plan §7; correct tool, valid schema, expected arguments.
- **Investigation:** the Investigator flow with fake tool results: several tool calls, then a JSON answer that must contain the key facts (41 days at Ospedale B, 34 free slots at Ospedale C, Cooperativa 3 at 52%).

| Model | Licence | RAM | Speed | Italian | Tools | Investigation (v2 prompt) | Verdict |
|---|---|---|---|---|---|---|---|
| `qwen3:30b-instruct` (MoE, 3B active) | Apache 2.0 | 18 GB | 10.8 tok/s | **5/5**, 11.5 s each | 4/5, 18 s | **Pass**, 243 s, all facts right | **Recommended: all cached agents** |
| `qwen3:4b-instruct` | Apache 2.0 | 2.5 GB | **14.3 tok/s** | 4/5, 8.1 s each | 3/5, 15 s | Pass, 244 s | **Recommended: short live text, behind templates** |
| `nemotron-3.5-lightning:30b` (MoE, 3B active) | NVIDIA Open Model | 25 GB | 5.6 tok/s | 5/5, 24.4 s | 4/5, 67 s | Pass, 394 s | Backup only: too heavy for 32 GB next to the app |
| `qwen3:8b` | Apache 2.0 | 5.2 GB | 5.6 tok/s | 4/5 | 5/5 | Fail (v1): invented an ASST, missed key facts | Not recommended: slower and weaker than 30B MoE |
| `qwen2.5:7b` | Apache 2.0 | 4.7 GB | 5.7 tok/s | 4/5; wrote "Medico di Maggiore Grado" for MMG | 5/5 | Fail (v1): invented an ASST | Not recommended |
| `qwen2.5:14b` | Apache 2.0 | 9.0 GB | 3.2 tok/s | 4/5; **inverted Maria's fact** ("continua la terapia con furosemide") | 5/5 | Fail (v1), 408 s | Not recommended |
| `mistral-nemo:12b` | Apache 2.0 | 7.1 GB | 3.6 tok/s | 5/5 | 4/5 | Fail (v1): **called no tools**, answered from nothing | Not recommended |

How to read it:

- **No model is fast enough live for the Investigator on our laptops.** The best investigation took 243 s against the 30 s target (AC5). Every investigation shown in the demo comes from the cache (D12, D14).
- **The 30B MoE model beats every dense model** because only 3B parameters are active per token. It is faster than the 7B and 8B dense models and is the only one with every Italian text right.
- **The prompt matters as much as the model.** With the first summary prompt ("riassumi in JSON"), 6 of 7 models dropped the 34 free slots at Ospedale C, which is the fact the reschedule action needs. With a prompt that asks for every relevant number, all three candidates passed. Prompts are versioned in the gateway (`prompt_version`) for this reason.
- **Every model made at least one factual slip somewhere:** inverted meaning, a wrong hospital in a call script, an invented ASST, "within 30 days" instead of 21, or adherence presented as the cause of the wait. Facts come from code (principle 2), and the Verifier stays in scope.
- **One question is ambiguous, not wrong:** every model read "per gruppo di MMG" as `grouping=mmg` instead of `mmg_group`. Fix the question or the tool description before scoring AC6.
- **Speeds vary by about ±40% on the same laptop** with load and power mode (7B measured 9.0 and 5.7 tok/s on two runs). Measure on mains power with nothing else running.

Limits of this evaluation: one run per prompt and 5 prompts per test, on fake tool results. AC6 (10 benchmark questions × 3 scenarios on real simulator data) is the real gate in week 3.

## 4. Roles

| Role | Owns | Accepts |
|---|---|---|
| R1 Data & simulator | simulator, 3 scenarios, Maria, calibration, diabetes data (option B) | AC8, AC13, AC14 |
| R2 Analytics & ML | state engine, views, Risk, what-if, PNE forecast, Enrollment rules, Bed Finder ranking | AC2–AC4, AC12, AC15–AC18 |
| R3 AI agents | all LLM agents, LLM gateway, cache, action service, autonomy, Verifier, prompt log | AC1, AC5–AC7, AC10, AC11, AC19 |
| R4 Console | all screens, WebSocket client, demo bar, offline assets | supports AC9 |
| R5 Spec, domain & demo | SPEC.md, contracts, PDTA texts, Italian terminology, demo script, runbook, presentation | AC9, AC ordering |

The critical path is R1 and R5 in week 2.

---

## 5. Phase 0 — Foundations (Week 1)

**Goal:** everyone can run the same stack from a clean clone, the models are chosen on measured numbers, and the shape of the system is agreed.

**Entry:** repo exists (done), Solution Plan approved.

| # | Step | Owner | Output | Done when |
|---|---|---|---|---|
| 0.1 | Team charter: roles R1–R5, two 20-min syncs a week, chat channel, decision-register owner (R5) | All | `brief/charter.md` | Signed off by all five |
| 0.2 | Approval check: confirm with the mentor that Ollama, the chosen models and every tool in §10 are allowed; confirm with IT that Ollama and Python may run on company laptops | R5 | Line in decision register | Written "yes" from mentor and IT |
| 0.3 | Dev setup guide: `uv sync`, Ollama install, `ollama pull`, PATH fix for terminals opened before install, run the benchmark | R3 | `README.md` "Getting started" | A second person follows it on a clean laptop without help |
| 0.4 | Model selection: run `llm_eval.py` (5 Italian, 5 tool-calling prompts, one investigation) on the candidates with no other load; R5 reads the Italian outputs for factual faithfulness. **Done on the reference laptop (§3.1); D11 recommended.** Remaining: R5 review of the Italian outputs, and one rerun on a second laptop | R3, R5 | Table of tok/s, tool-call accuracy and faithfulness per model; decision D11 | One small model (live text, Daily Worklist) and one larger model (cache generation for Investigator, Pathway Builder, Rule Advisor) chosen |
| 0.5 | Demo machine decision: identify the fastest machine available (GPU if anyone has one); it becomes the cache-generation and demo machine; name a backup laptop. **Decided (D12):** every team laptop is the reference laptop, none has a GPU | R5, R3 | Decision D12 | Two named machines |
| 0.6 | Repo skeleton exactly as in Solution Plan §15: `brief/ spec/ src/{sim,engine,agents,api,ui}/ testing/ demo/`; `sim`, `engine`, `agents` and `api` are separate Python packages installed by `uv sync`; `carepath-api` entry point | R4 | Skeleton PR | `uv run pytest` passes |
| 0.7 | API skeleton: FastAPI app, `GET /api/health`, WebSocket `/api/stream` that emits a fake tick every 2 s; serves the built console | R4 | `src/api/main.py` | Browser shows a ticking counter |
| 0.8 | Frontend decision. Streamlit is not recommended because it cannot reproduce the prototype layout. **Decided (D13):** React 19 + TypeScript on Vite 8, Node 24 via fnm; console shell in `src/ui` | R4 | Decision D13 | Recorded with reason |
| 0.9 | DuckDB skeleton: database file layout, empty tables from the draft contracts, state-engine stub | R2 | `src/engine/db.py` | Tables created by one command |
| 0.10 | Simulator sketch: list of comuni in ASST Mantova, Cremona and Crema; ISTAT population by age and sex; published PNE 30-day HF readmission range; Ospedale A/B/C mapped to ASSTs | R1 | `src/sim/README.md` with sources and numbers | Reviewed by R5 |
| 0.11 | Problem brief and SPEC draft: users, pains, success metrics; draft of every contract in §6 of this plan | R5 | `brief/problem.md`, `spec/SPEC.md` draft | Reviewed at the second sync |

**Exit gate:** a clean clone runs the hello stack and the benchmark. Models and the demo machine are chosen with numbers (D11, D12). SPEC draft has been reviewed.

**Risks:** IT blocks local installs → escalate on day 1 and develop on a personal machine with synthetic data only. No GPU anywhere → accept CPU, rely on the cache, and start cache warm-ups earlier (week 3, day 3 instead of week 4).

---

## 6. Phase 1 — Spec, contracts and simulator (Week 2, scope gate)

**Goal:** contracts are frozen, and the simulator for heart failure, with 3 scenarios and Maria, provably contains patterns 1–3, is calibrated to PNE, and runs a day in under 1 s.

**Entry:** Phase 0 exit gate passed.

### 6.1 Spec and contracts (R5 leads, all review)

| # | Step | Owner | Output | Done when |
|---|---|---|---|---|
| 1.1 | Data contracts: `events` (11 columns per Solution Plan §6), `patients`, `facilities`, `capacity_slots`, `beds` (optional), `scenario_truth`; types, keys, allowed codes | R5, R1 | SPEC §Data | R1 and R2 sign off |
| 1.2 | State and view contracts: `pathway_state` (one row per patient × pathway; status `on_track` / `due_soon` / `overdue` / `dropped`), `kpi_daily`, `sankey_flows`, `map_comuni`, `worklist_today` | R5, R2 | SPEC §State | R2 and R4 sign off |
| 1.3 | Pathway model JSON schema plus `hf_lombardia_v1.json` (eligibility, steps, due/every days, rules); codes confirmed by the Italian colleague | R5, R2 | `spec/pathways/` | Validates against the schema in a test |
| 1.4 | Tool signatures (Solution Plan §7): all take `pathway_id`, read-only, typed return JSON; the error contract | R5, R3 | SPEC §Tools | R3 signs off |
| 1.5 | Action contract: types (`notify_mmg`, `reschedule`, `call_task`, `enroll_proposal`, `rule_proposal`, `pathway_proposal`, `bed_proposal`, `bed_assignment`), autonomy levels 0–3, status lifecycle, evidence list | R5, R3 | SPEC §Actions | R3 signs off |
| 1.6 | API and WebSocket contract: REST endpoints from Solution Plan §7; WS envelope `{type: tick\|alert\|action\|investigation, scenario, day, payload}` | R5, R4 | SPEC §API | R4 signs off |
| 1.7 | Acceptance criteria AC1–AC19 copied into SPEC with owner, measurement method and test file name | R5 | SPEC §Acceptance | Each AC has a test stub in `testing/` |
| 1.8 | PDTA texts in Italian: heart failure (final), type 2 diabetes (draft) | R5 | `spec/pdta/` | Reviewed by the Italian colleague |
| 1.9 | **Contract freeze** at the end of day 2; later changes only via the sync and the decision register | R5 | Tag `spec-v1` | Tag pushed |

### 6.2 Reference data (R1)

| # | Step | Output | Done when |
|---|---|---|---|
| 1.10 | Download ISTAT comune list, population by age band and ISTAT code for the 3 ASSTs; store as CSV with source URL and licence | `src/sim/data/comuni.csv` | Totals match ISTAT for each ASST |
| 1.11 | Download comune boundaries, clip to the 3 ASSTs, simplify to under 2 MB GeoJSON for the offline map | `src/ui/assets/comuni.geojson` | Renders offline in a test page |
| 1.12 | Facility table: Ospedale A, B, C and clinics, placed in real ASSTs, with capacity per service (echo, cardiology visit, lab) | `facilities.csv` | Reviewed by R5 |
| 1.13 | Distance matrix comune → facility, precomputed once (haversine × road factor ~1.3; OSRM only if accuracy is challenged); never queried live | `distances.parquet` | Maria's comune shows about 45 km to her hospital |

### 6.3 Simulator (R1)

| # | Step | Output | Done when |
|---|---|---|---|
| 1.14 | Population generator: 10,000 HF patients sampled by comune and age; lives alone; distance; MMG assignment; MMG grouped into cooperatives with a Centro Servizi | `patients` table | Distributions plotted in the notebook |
| 1.15 | Daily vectorised step (numpy and pandas, fixed seed): discharges, visits, imaging, labs, dispensing, telemonitoring readings, admissions; capacity-driven waits from `capacity_slots` | `src/sim/step.py` | 365 days for 10k patients run; one day under 1 s (early AC2) |
| 1.16 | Outcome model: readmission hazard rising with non-collection, missed visits, long waits, distance and living alone; calibrated so 30-day HF readmission falls inside the published PNE range | Config with every assumed probability | Notebook shows the rate inside the range |
| 1.17 | Patterns 1–3 parameterised per scenario: echo bottleneck at one hospital with free slots at another; one MMG group with low furosemide collection; rural cluster (lives alone, more than 40 km) dropping telemonitoring | `src/sim/scenarios/{1,2,3}.yaml` | Same pattern types, different locations per scenario |
| 1.18 | `scenario_truth` written to a separate path; agent tools are given a DuckDB connection without that table; a test asserts it | `demo/truth/` + test | Test fails if any tool can read it |
| 1.19 | Maria: scripted trajectory present in all 3 scenarios; without agents she is readmitted on day 47; with agents a day-31 call leads to delivery on day 33, HbA1c on day 40 and no readmission | Maria overrides + test | AC14 passes 10 runs out of 10 |
| 1.20 | Action feedback hook: an executed action on day D becomes events on day D+1 (interface plus a no-op implementation) | `src/sim/feedback.py` | R3 can call it |
| 1.21 | Pattern-proof notebook: for each scenario shows patterns 1–3 and the PNE calibration from data alone | `testing/notebooks/patterns.ipynb` | R5 reviews; this is the gate evidence |

### 6.4 Parallel work in week 2

| # | Step | Owner | Output |
|---|---|---|---|
| 1.22 | State engine over simulator output: incremental `pathway_state` update for patients with new events plus a deadline sweep; `kpi_daily` | R2 | `src/engine/state.py` |
| 1.23 | Fixtures for every contract (one small scenario) so R3 and R4 never wait | R2 | `testing/fixtures/` |
| 1.24 | Tools v1 against fixtures; 10 benchmark questions with expected answers per scenario | R3 | `src/agents/tools.py`, `testing/benchmark/` |
| 1.25 | Screens on fixtures: Storia di Maria, Buste, Panoramica, Attività agenti side panel | R4 | `src/ui/` |

**Scope gate (end of week 2):** the pattern notebook passes for all 3 scenarios, Maria is stable (AC14), one simulated day runs in under 1 s, and SPEC `spec-v1` is tagged.
**If it fails:** option B (diabetes) moves to a slide immediately; generic contracts stay; R1 keeps working on the simulator in week 3 and R2 takes the state engine alone.

---

## 7. Phase 2 — Core build (Week 3, days 1–5)

**Goal:** the complete demo flow (steps 1–7, 9, 10) runs end-to-end every day on real simulator data, with the cache in place.

**Entry:** scope gate passed, or failed with the cut applied.

**Daily rule:** at the end of each day, R5 runs the whole flow on the main branch. Whatever breaks is the first task the next morning.

### 7.1 Engine and analytics (R2)

| Day | Step | Output | Done when |
|---|---|---|---|
| 1 | 2.1 Real-time tick loop in the order of Solution Plan §9: sim emits day D → state update → Risk on changed patients → Monitoring → refresh views → Intervention → Daily Worklist → Investigator (async) → WS push | `src/engine/tick.py` | 1 day under 1 s for 10k patients (AC2) |
| 1 | 2.2 Views `sankey_flows`, `map_comuni` | DuckDB views | Under 200 ms each (AC3) |
| 2 | 2.3 Risk model: XGBoost trained once offline on a separate seed; model file versioned; top-3 drivers per patient | `src/engine/risk.py`, `models/risk.json` | AUC reported in notebook; scoring on a tick within budget |
| 2 | 2.4 `worklist_today`: one row per patient across pathways, ranked by risk, all reasons, escalation step | View + test | Top 20 contain at least 15 high-risk or overdue patients (AC12 data side) |
| 3 | 2.5 What-if: run the simulator forward 6 months with changed levers (echo capacity, telemonitoring deadline), with and without agents, same seed | `src/engine/whatif.py` | Under 10 s (AC4) |
| 5 | 2.6 PNE forecast to year end, with and without CarePath, plus a lever | `src/engine/pne.py` | Numbers shown on step 7 come from here |

### 7.2 Agents and control (R3)

| Day | Step | Output | Done when |
|---|---|---|---|
| 1 | 2.7 **LLM gateway**: one function used by every agent; temperature 0, seed, JSON schema via Ollama structured output, 1 retry, 20 s timeout, cache key `(agent, model, prompt_version, input_hash)`, cache-only switch, one JSON log line per call (agent, model, latency, cache hit, valid) | `src/agents/llm.py`, `demo/cache/`, `logs/llm.jsonl` | Unit tests for hit, miss, timeout and invalid JSON |
| 1 | 2.8 Monitoring (rules from pathway JSON; regional alarm when the same deviation exceeds a threshold at one facility) and Risk wired to the tick | `src/agents/monitoring.py` | Echo alarm for Ospedale B fires around day 35 in scenario 2 |
| 2 | 2.9 Investigator: tool-only loop, max 6 steps, emits a JSON list of claims, each with the tool call that supports it; no SQL | `src/agents/investigator.py` | Finds pattern 1 in all 3 scenarios without hints (AC1 part) |
| 3 | 2.10 Benchmark run: 10 questions × 3 scenarios; scoring script; results stored per prompt version | `testing/benchmark/run.py` | At least 8 of 10 correct (AC6) |
| 3 | 2.11 Cache warm-up v1 on the demo machine for all 3 scenarios | Cache files | Investigator from cache under 2 s (AC5) |
| 4 | 2.12 **Action service**: single writer; autonomy level per action type; guardrails from Solution Plan §8 (no therapy, no diagnosis, daily limit per facility); audit log; undo; feeds the simulator via the feedback hook | `src/agents/actions.py` | No action above its level executes without approval (AC7) |
| 4 | 2.13 Intervention: rules choose the action (reminder, call task, notify MMG, reschedule to the earliest free slot then distance); small model writes the rationale from a template | `src/agents/intervention.py` | With-agents run has fewer readmissions on the same seed (AC8) |
| 5 | 2.14 Reporter: monthly Italian report in PNE style; numbers from views, LLM for sentences only | `src/agents/reporter.py` | Report numbers equal the view numbers (test) |
| 5 | 2.15 Pathway Builder lite: Italian PDTA text → pathway JSON → schema validation → retry → manual JSON fallback | `src/agents/pathway_builder.py` | HF PDTA reproduces `hf_lombardia_v1.json` |

### 7.3 Console (R4)

| Day | Step | Done when |
|---|---|---|
| 1 | 2.16 WebSocket client; Mappa from local GeoJSON (fallback: comune table, as in the prototype); Percorsi (Sankey) | Map recolours each tick, offline |
| 2 | 2.17 Chiedi (investigation steps appear one by one, "verificato" badge slot); Paziente 360 (timeline, with/without toggle) | Driven by real API data |
| 3 | 2.18 Impostazioni (autonomy per action type); Approvazioni (queue, approve and reject call the API) | Approve in UI changes the audit log |
| 4 | 2.19 What-if screen (sliders, run, results); Confronto split screen with counters | Matches §7.1 outputs |
| 5 | 2.20 Lista chiamate; **demo bar** (hidden; hotkeys for scenario 1/2/3, pause, speed, jump to day, cache-only, reset); cache indicator visible to the team only | Operator can run the whole script with hotkeys |

### 7.4 Spec, tests and demo (R5)

| Day | Step |
|---|---|
| 1 | 2.21 Acceptance tests from AC stubs, run locally with `uv run pytest -m acceptance` |
| 2 | 2.22 Check AC1–AC3 on real data; file defects |
| 3 | 2.23 **Checkpoint:** core runs end-to-end? Decide which optional layers enter (Phase 3) |
| 4 | 2.24 Demo script v1: trigger sentences, operator clicks, timings from Solution Plan §11 |
| 5 | 2.25 Technical review with the mentor |

**Exit gate (end of week 3):** steps 1–7, 9 and 10 of the demo run end-to-end on simulator data with the cache. AC1–AC8, AC13, AC14 and AC17 have passing or measured tests.

---

## 8. Phase 3 — Gated extensions (Week 3, days 3–5, in parallel)

**Entry:** checkpoint on day 3 says the core runs end-to-end. Extensions are added **in this order**. Each one is cut as a whole if it is not demo-ready by the end of week 3.

| Order | Extension | Steps | Owner | AC | Demo step |
|---|---|---|---|---|---|
| 1 | Verifier | Re-run the tool behind each Investigator claim; compare with tolerance; label `verificato` or correct; test set of 5 answers with injected wrong numbers | R3 | AC10 | 5 |
| 2 | Rule Advisor | From an investigation finding, propose a rule in pathway-rule format; on approval Monitoring loads it the next day | R3 | AC11 | 5 |
| 3 | Daily Worklist | Ranking from `worklist_today` (code); small model writes an Italian call script for the top 20 only; call outcome field | R2, R3 | AC12 | 9 |
| 4 | Option B: diabetes | R1: diabetes population (~3,000, ~900 overlapping), patterns 4–5, Maria on both pathways. R2: Enrollment rules, KPIs for the second pathway with no code change. R3: Pathway Builder on diabetes PDTA, Enrollment Advisor rationale. R4: Nuova patologia screen | R1–R4 | AC15, AC16, AC17 | 8 |
| 5 | Bed Finder | Only if time remains after day 4. R1: `beds` and occupancy from admissions and discharges. R2: `free_beds` and ranking (diagnosis → ward, same hospital first, then distance). R3: two modes, assign (default) and propose-and-confirm, with audit and undo. R4: Posti letto screen | R1–R4 | AC18, AC19 | 9c |

**Cut order if anything slips** (Solution Plan §4): Bed Finder → option B → optional agents → parallel what-if → Pathway Builder (manual JSON stays) → map (comune table stays).

---

## 9. Phase 4 — Stabilisation and demo readiness (Week 4)

**Goal:** the demo runs 10 times in a row, offline, on the main and the backup machine.

| Day | Step | Owner | Done when |
|---|---|---|---|
| 1 | 4.1 Feature freeze; only bug fixes merge from now on | All | Branch protection on `main` |
| 1 | 4.2 Measure AC2–AC5, AC12, AC16 on the demo machine; profile and fix the slowest path | R2, R3 | All within target |
| 2 | 4.3 Final cache warm-up for all 3 scenarios with the larger model; cache files hashed and copied to the backup laptop | R3 | Hash list matches on both machines |
| 2 | 4.4 Offline hardening: fonts (IBM Plex, OFL) and all JS in the repo; grep proves no `http` asset URLs; full run with the network adapter disabled | R4 | Offline run passes |
| 2 | 4.5 Record the backup video of a full run (OBS) | R4 | Video on both machines |
| 3 | 4.6 Rehearsals with the mentor picking the envelope; timing per step; Italian colleague reviews every on-screen term and the report | R5 | Under 7 min; terms approved |
| 4 | 4.7 10 consecutive runs; log every cache fall-back and stop | All | AC9: 10 of 10 without a stop |
| 4 | 4.8 Final package: SPEC, code, tests, prompt log, decision register, retrospective | R5 | Tagged release `demo-v1` |
| Show day | 4.9 Runbook from Solution Plan §12: T−24h full rehearsal, T−60 min network off and models warmed, T−30 min projector check, T−5 min reset and start 3 scenarios | R4, R5 | — |

**Fallbacks during the demo:** Investigator silent for 10 s → cache-only hotkey. Alarm late → jump to day 34. UI frozen → reload (state is on the server). Machine down → backup laptop, same scenario, jump to the same day. Both down → video.

---

## 10. Zero-cost bill of materials

| Need | Choice | Cost and licence note |
|---|---|---|
| Language and env | Python 3.12, uv | Free, open source |
| Data and ML | numpy, pandas, DuckDB, scikit-learn, XGBoost | Free, open source |
| API | FastAPI, uvicorn, WebSocket | Free, open source |
| Console | React, TypeScript, Vite, Node 24 via fnm | Free, open source |
| LLM runtime | Ollama | Free, open source |
| Models | Qwen 3 30B-A3B Instruct and Qwen 3 4B Instruct (Apache 2.0), D11 | Free; backup Nemotron 3.5 Lightning under the NVIDIA Open Model License, which allows commercial use |
| Agent orchestration | Plain Python with tool calling | Replaces LangGraph: fewer dependencies |
| Prompt and call log | JSON lines in the repo | Replaces Langfuse, which needs Docker and several services |
| Map | ISTAT boundaries as GeoJSON, drawn without a basemap | No tile server, works offline |
| Distances | Precomputed once | No live calls to public OSM servers |
| Fonts | IBM Plex (OFL), bundled | No Google Fonts at runtime |
| Notebooks | JupyterLab | Free |
| Video | OBS Studio | Free |
| Repo | GitHub private repo | Free tier |
| Process mining | pm4py, notebook only, optional | Not needed for the demo |
| Voice input | Dropped | Typing plus the 10 benchmark questions |

The only real cost is hardware. Without a GPU machine, the plan still works because of the cache, at the price of slower cache generation.

## 11. Cross-cutting rules

**Definition of done** (Solution Plan §15): code reviewed by one other role, tests pass, its AC is met, it works in the end-to-end flow, and the prompt log is updated if AI was used.

**Branching:** trunk-based; short-lived branches `r<role>/<topic>`; pull requests into `main` reviewed by one other role. Commit messages say what changed, not "refactor" boilerplate. No force-pushes to `main`.

**Testing layers:**

- Unit tests for the state engine, rules, tools, gateway and action service.
- Data tests: the pattern notebook plus asserts that run in pytest.
- Agent evaluation: 10 benchmark questions × 3 scenarios, plus the Verifier injection set, stored per prompt version.
- Performance tests: timers for AC2–AC5, AC12, AC16 on the demo machine.
- End-to-end: the full demo script, scripted through the API, every day from week 3.

**Decision register** (continues D1–D10 from the Solution Plan):

| # | Decision | Status |
|---|---|---|
| D11 | `qwen3:30b-instruct` for every cached LLM output (Investigator, Pathway Builder, Rule Advisor, Reporter, Verifier wording); `qwen3:4b-instruct` only for short live text that code fills from templates (action rationales, call-script wording). Both Apache 2.0, both fit in RAM together (about 21 GB of 32 GB). Plain `qwen3:4b` and `qwen3:30b` tags are thinking models and are not allowed. Backup: `nemotron-3.5-lightning:30b`, not kept on disk; pull it again only if both Qwen models fail. Evidence in §3.1 | Recommended 26 Oct 2026; confirm at the week-1 sync |
| D12 | No GPU in the team: every laptop is the reference laptop (§3). One team laptop is the demo machine and generates the cache unattended (overnight runs if needed); a second identical laptop is the backup, with the same models and a hash-checked copy of the cache. Live LLM is never on the critical path | Decided 26 Oct 2026 |
| D13 | Console in React 19 + TypeScript on Vite 8, not Angular. Reasons: the prototype's screens port almost one-to-one into components; far less boilerplate for a one-week build; AI assistants generate React most reliably; the build is static files that FastAPI serves offline. Node 24 LTS via fnm (`src/ui/.node-version`), because the laptops' Node 20 is too old for Vite 8. All API paths under `/api` so one proxy rule separates API from console. Charts, Sankey and the GeoJSON map with one library chosen in week 2 (candidate: Apache ECharts, bundled locally) | Decided 26 Oct 2026 |
| D14 | Cache-first LLM: every demo LLM output is pre-generated; live is optional | Proposed |
| D15 | Plain Python agents instead of LangGraph; JSON log instead of Langfuse | Proposed |
| D16 | Offline map from ISTAT GeoJSON, no basemap; distances precomputed | Proposed |

## 12. Acceptance criteria map

| AC | Criterion (short) | Phase | Owner |
|---|---|---|---|
| AC1 | Agents find patterns 1–3 without hints | 2 | R3 |
| AC2 | Simulated day under 1 s | 1 (early), 2 | R2 |
| AC3 | KPI, Sankey, map under 200 ms | 2 | R2 |
| AC4 | What-if 6 months under 10 s | 2 | R2 |
| AC5 | Investigator under 30 s live, under 2 s from cache | 2 | R3 |
| AC6 | At least 8 of 10 benchmark questions correct | 2 | R3 |
| AC7 | No action above its autonomy level without approval | 2 | R3 |
| AC8 | Fewer readmissions with agents, same seed | 2 | R1 |
| AC9 | 10 consecutive demo runs without a stop | 4 | R5 |
| AC10 | Verifier catches all injected wrong numbers | 3 | R3 |
| AC11 | Rule Advisor rule fires alarms the next day | 3 | R3 |
| AC12 | Worklist under 30 s; 15 of top 20 high-risk or overdue | 3 | R2 |
| AC13 | Correct ASST, comune group and MMG group in all 3 scenarios | 1 (data), 2 (agents) | R1 |
| AC14 | Maria's trajectory identical on every run | 1 | R1 |
| AC15 | Enrollment finds at least 90% of pattern-5 candidates | 3 | R2 |
| AC16 | New pathway to compliance under 60 s | 3 | R2 |
| AC17 | Same tools, KPIs and console for both pathways | 2 | R2 |
| AC18 | Bed Finder under 3 s, correct ward, bed really free | 3 | R2 |
| AC19 | Confirm mode writes nothing without confirmation; assign mode audited and undoable | 3 | R3 |

## 13. Open questions

1. Has IT confirmed that Ollama and local models are allowed on company laptops? (Blocks step 0.2.)
2. When is the Italian colleague available for the PDTA and terminology reviews in weeks 2 and 4?
3. Has the TL confirmed the positioning given that ENG's healthcare portfolio was sold? (Solution Plan §17.)
