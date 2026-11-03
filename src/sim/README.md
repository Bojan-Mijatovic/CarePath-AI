# Simulator sketch

Owner: R1. Delivery plan step 0.10. Last updated: 28 Oct 2026.

This page fixes the real-world numbers the simulator is built on: which comuni belong to which ASST, how many people live there by age and sex, and which readmission range the outcome model must hit. Step 1.10 turns it into `src/sim/data/comuni.csv`; steps 1.12 and 1.13 add facilities and distances.

## 1. Territory

ATS della Val Padana covers the provinces of Mantova (MN) and Cremona (CR): **177 comuni** in the ISTAT list of 28 Oct 2026.

| ASST | Comuni | Rule |
|---|---|---|
| `asst_mantova` | 64 | every comune of the province of Mantova |
| `asst_cremona` | 65 | the comuni in the ATS list "Elenco Comuni ASST Cremona" (27 Mar 2022): distretto Cremona, including the Viadana-Casalmaggiore ambito |
| `asst_crema` | 48 | every other comune of the province of Cremona |

Check: the ATS describes the Crema district as 48 comuni, which is what the rule gives. All 65 names in the ATS list match an ISTAT comune (compared without accents, case or punctuation).

## 2. Population (ISTAT, 1 Jan 2025)

| ASST | Population | Males | Females | 65+ | 75+ | 85+ |
|---|---|---|---|---|---|---|
| `asst_mantova` | 407,744 | 202,415 | 205,329 | 100,761 (24.7%) | 53,423 (13.1%) | 17,390 |
| `asst_cremona` | 192,424 | 95,642 | 96,782 | 50,578 (26.3%) | 27,459 (14.3%) | 9,391 |
| `asst_crema` | 161,499 | 80,286 | 81,213 | 39,879 (24.7%) | 20,043 (12.4%) | 6,006 |
| **ATS** | **761,667** | **378,343** | **383,324** | **191,218 (25.1%)** | **100,925 (13.3%)** | **32,787** |

Population 65+ by age band and sex (males / females):

| ASST | 65–74 | 75–84 | 85+ |
|---|---|---|---|
| `asst_mantova` | 22,532 / 24,806 | 15,885 / 20,148 | 5,930 / 11,460 |
| `asst_cremona` | 11,217 / 11,902 | 7,877 / 10,191 | 3,073 / 6,318 |
| `asst_crema` | 9,593 / 10,243 | 6,494 / 7,543 | 2,096 / 3,910 |

Reference comuni: Mantova 49,607; Cremona 70,922; Crema 34,012; Casalmaggiore 15,095.

**10,000 HF patients is plausible.** It is 1.3% of the ATS population and 5.2% of people aged 65+. A heart-failure prevalence of 1–2% in adults is the figure usually cited for Europe. If the patients are spread in proportion to the population aged 65+, that gives about 5,269 in Mantova, 2,645 in Cremona and 2,086 in Crema. Step 1.14 will weight older bands more heavily, which moves a few hundred patients towards Cremona, the oldest ASST. The age weights are an assumption, written in the simulator config.

## 3. Hospitals

Facility names are invented (Solution Plan D7); the comuni are real.

| Facility | ASST | Placed in | Notes |
|---|---|---|---|
| `osp_A` "Ospedale A" | `asst_mantova` | Mantova (020030) | Maria's hospital (demo step 9c) |
| `osp_B` "Ospedale B" | `asst_cremona` | Cremona (019036) | echo bottleneck in scenario 2 (SPEC §3.3) |
| `osp_C` "Ospedale C" | `asst_crema` | Crema (019035) | free echo slots in scenario 2 |

Each scenario puts the bottleneck at a different hospital (Solution Plan §11).

**Clinics and capacity (step 1.12):** `data/facilities.csv` and `data/capacity.csv`. A facility sits at the centroid of its comune, so the distances of step 1.13 agree with the map.

| Facility | ASST | Comune | Echo | Cardio visit | Lab |
|---|---|---|---|---|---|
| `osp_A` Ospedale A | Mantova | Mantova | 6 | 3 | 37 |
| `osp_B` Ospedale B | Cremona | Cremona | 3 | 2 | 24 |
| `osp_C` Ospedale C | Crema | Crema | 3 | 2 | 22 |
| `amb_1` Poliambulatorio 1 | Mantova | Castiglione delle Stiviere | — | 2 | 15 |
| `amb_2` Poliambulatorio 2 | Mantova | Viadana | — | 1 | 10 |
| `amb_3` Poliambulatorio 3 | Mantova | Suzzara | — | 1 | 13 |
| `amb_4` Poliambulatorio 4 | Cremona | Casalmaggiore | — | 1 | 7 |
| `amb_5` Poliambulatorio 5 | Cremona | Soresina | — | 1 | 7 |
| `amb_6` Poliambulatorio 6 | Crema | Rivolta d'Adda | — | 1 | 8 |

Slots per simulated day; the PoC has no weekly cycle. Only hospitals do echo, so pattern 1 is a hospital-to-hospital comparison. No facility is in the Oltrepò, which keeps Maria's area far from services (pattern 3).

How the slots were sized. All of these are assumptions, which `testing/test_sim_facilities.py` checks and step 1.16 recalibrates:

- Patients per ASST in proportion to the population aged 65+: 52.7% Mantova, 26.5% Cremona, 20.9% Crema.
- 0.33 HF discharges per patient per year, including readmissions. Each discharge needs one echo (due in 90 days) and one cardiology visit (due in 30 days), as in the pathway of SPEC §4. That gives 4.76, 2.39 and 1.89 per day.
- A BNP test every 90 days for every patient: 58.5, 29.4 and 23.2 per day.
- Capacity is at least 1.25 × demand **at every facility**, with demand routed the way the simulator routes it: each patient uses the nearest facility of their own ASST that offers the service. Step 1.15 showed that ASST totals are not enough: with the first table all of Cremona city queued at `osp_B` for cardiology visits, 53 days on average, before any scenario. The base table has no bottleneck; each scenario creates one (step 1.17), for example by cutting `osp_B` echo from 3 to 1 slot a day while `osp_C` keeps spare slots.

**Maria's comune: Poggio Rusco** (020042, 6,535 residents, `asst_mantova`), 44.8 km by road from `osp_A` (step 1.13). The nearest facility of any kind is `amb_3` at 42.8 km. The other candidates did not fit: Ostiglia is 36.3 km from `osp_A` and Sermide e Felonica 55.6 km.

**Distances (step 1.13):** `data/distances.csv` gives comune centroid → facility for all 177 × 9 pairs: great-circle distance × 1.3 road factor, in km to 1 decimal. It is computed once and never queried live; OSRM only if the accuracy is challenged. A facility is 0 km from its own comune, a limit of comune-level resolution.

## 4. Calibration target: PNE 30-day HF readmissions

The indicator is PNE "Scompenso cardiaco congestizio: riammissioni ospedaliere a 30 giorni".

| Value | Scope | Source |
|---|---|---|
| **11.87%** | Italy, crude, 2024 data | PNE 2025, quoted in a hospital report (source 5) |
| 14.16% | Italy, crude, 2019 data, 93,382 cases | PNE 2020, as quoted by an AIOP report (search result; not re-checked) |
| 8.35%–19.99% | 5 hospitals in Catania, risk-adjusted, 2024 data | PNE 2025 (source 5) |
| 10.2% and 15.97% | a Milan hospital and ASP Crotone | Solution Plan §6 |

**Target for the baseline arm:** an ATS-wide 30-day HF readmission rate of about 12%, with every hospital inside 10–16%. The bottleneck hospital of a scenario may sit at the top of the range, but stays inside it. The agents arm must be lower on the same seed (AC8).

Definition gap, already in the limitations (SPEC §5.2): we count an unplanned admission within 30 days after an HF discharge. The PNE computes the outcome from the index admission date, with its own risk adjustment.

Not found: PNE values for the hospitals of ATS Val Padana. The PNE portal (pne.agenas.it) is interactive, so R5 can read them by hand if the team wants a local reference.

## 5. Sources

| # | Data | URL | Licence |
|---|---|---|---|
| 1 | ISTAT list of comuni (downloaded 28 Oct 2026) | https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv | CC BY 4.0 (https://www.istat.it/note-legali/) |
| 2 | ISTAT resident population by age, sex and marital status, 1 Jan 2025 (POSAS) | https://demo.istat.it/data/posas/POSAS_2025_it_Comuni.zip | CC BY 4.0 |
| 3 | ATS Val Padana, Elenco Comuni ASST Cremona (27 Mar 2022) | https://ats-valpadana.it/system/files/news/files/711/1166/Elenco%20Comuni%20ASST%20Cremona.pdf | public document; we use the names only |
| 4 | Agenas PNE, rationale of the HF indicators | https://pne.agenas.it/assets/documentation/razionali/Razionale_ind_59.pdf | public document |
| 5 | AOU Policlinico Rodolico–San Marco, PNE 2025 summary (2024 data), table with the Italy column | https://www.policlinicorodolicosanmarco.it/professionista/qualita-e-rischio-clinico/report/allegati/Riepilogo%20Treemap%20ed%20indicatori%20PNE%202025.pdf | public document |
| 6 | ISTAT generalised boundaries of comuni, 1 Jan 2026 (UTM 32N, despite the `_WGS84` file name) | https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2026/Limiti01012026_g.zip | CC BY 4.0 |

## 6. Open points for week 2

- Step 1.10, done: `uv run carepath-reference-data` downloads sources 1–2 plus ISTAT's province totals, writes `data/comuni.csv`, `data/population_by_age.csv` and `data/sources.csv`, and fails unless the comuni add up to ISTAT's province totals per age and sex. The ATS list (source 3) is transcribed in `data/asst_cremona_comuni.csv`.
- Step 1.11, done: the same command reads source 6, writes `lat`/`lon` (area centroid) into `data/comuni.csv` and the map file `src/ui/assets/comuni.geojson` (0.28 MB, no simplification needed, so neighbouring comuni share exact borders). `src/ui/map-test.html` draws it (`npm run dev`, then `/map-test.html`).
- The ATS list is from 2022. The script fails if any of its names is missing from the current ISTAT list, so a later merger of comuni shows up at once.

## 7. Population (step 1.14)

`sim.population.generate_patients(seed)` returns the `patients` and `mmg` tables of SPEC §3.2. Every random draw uses `sim.rng.component_rng(seed, "population")`, so the same seed gives the same population, byte for byte. The distributions are plotted in `testing/notebooks/population.ipynb`.

With seed 42: 10,000 patients, mean age 77.3, 57% women, 34% living alone, 853 patients more than 40 km from their hospital; 540 MMG in 16 cooperatives, about 18 HF patients per MMG.

| What | How | Assumption |
|---|---|---|
| Age, sex, comune | ISTAT cells (comune × sex × 5-year band, ages 45+) sampled with weight population × HF prevalence; age uniform inside the band | prevalence by band start: 45: 0.4%, 50: 0.6%, 55: 1%, 60: 1.5%, 65: 2.5%, 70: 4%, 75: 6%, 80: 9%, 85+: 12–15%. Only the relative weights matter |
| Lives alone | Bernoulli by age and sex | under 65: 15%; 65–74: F 30%, M 15%; 75–84: F 45%, M 20%; 85+: F 55%, M 30% |
| MMG | per comune, adults (15+) ÷ 1,300, rounded, at least one; a patient gets a random MMG of their comune | 1,300 adults per MMG (Lombardy ceiling 1,500) |
| Cooperative, Centro Servizi | within each ASST, comuni walked west to east and cut into groups of about 30 MMG; comuni are never split; one Centro Servizi per cooperative | 30 MMG per cooperative. Cremona city alone has 48 MMG, so it forms one cooperative |
| Reference hospital, distance | the hospital of the patient's ASST; road distance from `data/distances.csv` | — |
| Conditions | `['HF']`; Maria `['HF', 'T2D']`. Other T2D patients come with option B | — |
| Maria | `p_00001`, F, 81, Poggio Rusco, lives alone, 44.8 km from `osp_A`, in every seed | Solution Plan §6 |

Known limit: about 22% of patients live in the comune of their hospital (Mantova, Cremona, Crema) and get 0 km. If the risk model or the outcome model uses distance, step 1.16 should give them a small in-town distance instead.

## 8. Daily step (step 1.15)

`sim.step.Simulator.step(day)` returns the events of one day (SPEC §3.1); `uv run carepath-sim <run_id>` writes a whole run into `runs/<run_id>.duckdb` and reports the time per day.

**Design.** One numpy array per patient attribute, so a day is a few dozen vectorised operations. Every random draw comes from `component_rng(seed, "<component>:<day>")` and is drawn for all patients, so two arms of the same seed share their random numbers: changing one patient changes nobody else's events (tested). Step timing comes from the pathway JSON, capacity from `data/capacity.csv`; nothing in the code names the disease. A booking takes the first free slot at least 2 days ahead, so waits appear by themselves when demand exceeds capacity. A 120-day warm-up before day 0 is kept as history (SPEC C11).

**Measured** on the demo machine, seed 42, 365 days: 3.5–7.7 ms to simulate a day (two runs), 9–18 ms to write its events to DuckDB, about 2,900 events a day. Against the budgets in SPEC §9: AC2 allows 1,000 ms per day; the live tick at ×4 allows 500 ms for both arms; what-if allows 27–55 ms per arm-day. The simulator uses a small share of each.

Baseline behaviour, seed 42, days 0–364:

| Measure | Value | Target or note |
|---|---|---|
| HF discharges per patient-year | 0.31 | assumption 0.33 (step 1.12) |
| 30-day readmission rate | 7.9% before step 1.16; **12.0% after it** (§9) | about 12% |
| Cardiology visit within 30 days of discharge | 78% | |
| Echo within 90 days of discharge | 79% | |
| Mean wait from booking to slot | about 2 days at every facility | no bottleneck in the base table |
| Patients with at least one BNP in the year | 9,976 of 10,000 | |
| Patients sending telemonitoring readings | 3,224 in month 0, 2,581 in month 12 | dropout exceeds new starts; step 1.16 decides whether that is wanted |
| Overbooked slots; events during a hospital stay | 0; 0 | checked |

Behaviour assumptions (now in `config/baseline.json`, see §9): length of stay 1 + Poisson(7) days; 85% book each post-discharge step, 0–5 days after discharge; 92% attend; a periodic step is booked in the week before it is due, by 85%; 70% start telemonitoring, 1–10 days after discharge; 85% send a reading on a given day, 0.2% drop out a day; a 30-day drug supply, collected after it runs out with a daily chance drawn per patient from Beta(2, 3).

Not yet modelled: deaths, scenarios (1.17), Maria's script (1.19) and the effect of agents' actions (1.20).

## 9. Outcome model and calibration (step 1.16)

Every assumed probability is in `config/baseline.json`, validated by `sim.step.SimParams` (an unknown key is an error). Scenarios (step 1.17) will override single values.

**Decompensation.** Each day, a patient out of hospital starts to decompensate with probability

    h = admission_daily × (post_discharge_multiplier if discharged in the last 30 days) × exp(Σ β·x)

and is admitted 3–7 days later. During those days a telemonitored patient's weight rises by 0.7 kg a day, so the pathway rule `weight_gain_kg_3d >= 2` can see it: mean gain in the 3 days before an admission is 2.8 kg. This window is where agents can act (step 1.20, AC8).

| Risk factor x | β (log hazard) | Effect |
|---|---|---|
| No drug: supply ran out more than 3 days ago | 0.9 | ×2.5 (pattern 2) |
| A post-discharge step overdue, within 180 days of the discharge (includes waiting past the deadline) | 0.6 | ×1.8 (pattern 1) |
| Distance to hospital, per 10 km, capped at 60 km | 0.05 | ×1.22 at 40 km |
| Lives alone | 0.3 | ×1.35 |
| Per 10 years over 75 | 0.2 | ×1.22 at 85 |
| On telemonitoring | −0.3 | ×0.74 (pattern 3 works through dropout) |

**Calibration.** `uv run python -m sim.calibration` rescales `admission_daily` towards 0.33 discharges per patient-year and `post_discharge_multiplier` towards 12% readmission; it converged in 6 runs to 0.000561 and 5.47. Result (baseline arm, 365 days; plots in `testing/notebooks/calibration.ipynb`):

| Seed | ATS | `osp_A` | `osp_B` | `osp_C` | Discharges per patient-year |
|---|---|---|---|---|---|
| 42 | 12.0% | 12.2% | 11.7% | 11.9% | 0.330 |
| 7 | 11.5% | 12.1% | 10.5% | 10.9% | 0.333 |
| 2026 | 12.0% | 11.7% | 13.2% | 11.2% | 0.325 |

All inside the 10–16% range. Admissions per patient-year rise with each factor: 0.28 living with others against 0.43 alone; 0.29 within 10 km against 0.37 beyond 30 km; 0.27 under 75 against 0.42 at 85 and over.

Simulation time with the outcome model: 6.2 ms per day.

**Effects of actions** (step 2.13, `effects` in `config/baseline.json`). An action the action service executed on day D changes what its patients do from day D + 1, each patient with the chance its type gives (drawn with common random numbers, so both arms see the same draws). The payload names the effect (SPEC §9, C32). Maria is scripted and never reached.

| Effect | What changes | Reminder | Call | MMG notice |
|---|---|---|---|---|
| `collect` | collects the drug the next day | 0.20 | 0.35 | 0.30 |
| `book` | asks for a slot of the overdue step the next day | 0.20 | 0.35 | 0.30 |
| `start` | starts telemonitoring the next day | 0.15 | 0.30 | 0.20 |
| `review` | a decompensation under way ends without an admission | — | 0.25 | — |

A `reschedule` lists patients and moves each one's booking for the service from one facility to the first free slot of another when that slot is earlier, giving the old slot back. The values are assumptions, chosen so the agents arm lands in the range published for structured follow-up in heart failure. Measured over 120 days, seed 42, both arms on the same draws: 30-day readmissions −27% (scenario 1, 147 → 107), −25% (2, 150 → 112), −26% (3, 147 → 109); admissions −11% in each. A first set (reminder 0.3, call 0.6, review 0.6) gave −45%, too strong to be credible.

**Beds** (Bed Finder, D64, SPEC C42; `data/beds.csv` and `beds` in `config/baseline.json`). The simulator puts its patients in no ward, and the cohort is only the ATS's heart-failure patients, so a hospital's other patients are simulated apart: each ward has a share of its beds taken (cardiology 40%, internal medicine 62%, endocrinology 80%), drifting with AR(1) noise (sd 0.04 of the beds, 0.8 from one day to the next) from the generator `(seed, "beds")`; with a mean stay of 7 days, occupied × 2 ÷ 7 are expected to leave within 2 days. `Simulator.bed_occupancy()` writes the whole horizon into `bed_occupancy` once per run. Bed numbers were sized to the cohort's own inpatients, measured on scenario 2 without CarePath, days 0–63: Ospedale A 37 a day on average (26–53), B 23, C 18, half in cardiology and half in internal medicine. Ospedale A got 40 cardiology and 80 internal medicine beds, B 28 and 56, C 20 and 40, endocrinology 16, 10, 8. With 36 and 72 at Ospedale A both its wards were full on days 23 and 33. All of these are assumptions; no bed count of a real hospital is used.

## 10. Scenarios (step 1.17)

`scenarios/{1,2,3}.json`, validated by `sim.step.Scenario`, applied with `Simulator.apply_scenario` before the warm-up. `uv run carepath-sim s2_baseline` reads scenario 2 from the run id. The population is the same in all three; only the places of the patterns change. JSON instead of the planned YAML: same format and validation as `config/baseline.json`, no new dependency.

| | Scenario 1 | Scenario 2 | Scenario 3 |
|---|---|---|---|
| Pattern 1: echo bottleneck (slots a day) | `osp_A` 6 → 2 from day 0 | `osp_B` 3 → 1 from day 13 | `osp_C` 3 → 1 from day −58 |
| Pattern 1: spare echo slots | `osp_B` 3 → 5 | `osp_C` 3 → 5 | `osp_B` 3 → 5 |
| Pattern 2: cooperative collecting the drug less (×0.15 daily chance) | `coop_6` (ASST Cremona) | `coop_3` (ASST Crema) | `coop_11` (ASST Mantova) |
| Pattern 3: rural comuni where patients aged 70+, living alone, over 40 km away leave telemonitoring (dropout ×15, start ×0.3) | Casalasco: Martignana di Po, Tornata, Calvatone, Casalmaggiore, Rivarolo del Re ed Uniti, Spineda | Oltrepò: Poggio Rusco, Magnacavallo, Borgocarbonara, Sermide e Felonica | Alto Mantovano: Casalromano, Canneto sull'Oglio, Casalmoro, Solferino |

**Events** (step 2.26, D46). Besides its patterns, a scenario file may list `events`: known changes of the world, applied after the patterns in their order, so a later one wins where two overlap. The only type so far is `capacity`, the same shape as pattern 1 (`sim.step.CapacityChange`) with an optional `to_day`, the last day of the change; outside its window the capacity stays what it was. A renovation is 0 slots for a period; new devices are more slots from a day on.

```json
"events": [{"type": "capacity", "facility_id": "osp_A", "service": "echo", "slots_per_day": 0, "from_day": 40, "to_day": 60}]
```

Patterns are the hidden truth that `sim.truth` copies to `demo/truth/`; events are not, and `capacity_slots` shows them to the tools. The three demo scenarios have no events (D44), so their runs are unchanged byte for byte. What-if levers (step 2.5) reuse `Simulator.apply_capacity`.

The start days are set so the bottleneck's echo wait reaches about six weeks around day 35, when the alarm should fire (delivery plan step 2.8). Measured, seed 42, bookings made on days 30–40:

| | Scenario 1 | Scenario 2 | Scenario 3 |
|---|---|---|---|
| Echo wait at the bottleneck | 45 days | 39 days | 38 days |
| Echo wait elsewhere | 2 days | 2 days | 2 days |
| Drug collections a year, cooperative vs rest | 7.3 vs 11.2 | 7.5 vs 11.2 | 7.4 vs 11.2 |
| Admissions per patient-year, cooperative vs rest | 0.48 vs 0.33 | 0.44 vs 0.33 | 0.48 vs 0.33 |
| Pattern-3 patients, share on telemonitoring vs rest | 75, 1% vs 27% | 52, 4% vs 28% | 39, 3% vs 27% |
| 30-day readmission, ATS | 12.3% | 12.4% | 12.3% |

A booking further than 60 days away is refused (`max_wait_days`): the patient stays unbooked and the step becomes overdue, which raises their admission risk. That keeps the queue bounded and makes the bottleneck cost readmissions, which agents can then reduce by rescheduling to the hospital with spare slots (step 1.20).

Pattern 3 hits few patients (39–75) by design: they are a small group of comuni. Step 1.21 checks that the tools still see them.

## 11. Maria (step 1.19)

`sim/maria.py` scripts `p_00001`. Her state is set so no random process touches her and the script emits all of her events, so her path is the same in every scenario and seed (AC14, `testing/test_ac14_maria.py`: 10 runs, 5 seeds across the 3 scenarios × 2 arms). Her slots do not use facility capacity, so a scenario bottleneck cannot move her days.

| Day | Without agents | With agents (call on day 31) |
|---|---|---|
| −8 → 0 | HF admission at `osp_A`, discharged on day 0 | same |
| −120 … −30 | collects furosemide every 30 days; the supply runs out on day 0 | same |
| 3, 24 | cardiology visit booked, done on day 24 | same |
| 6 | telemonitoring starts, daily readings about 71.5 kg | same |
| 31 | 30 days without furosemide; HbA1c late | `CALL` "delivery_arranged" (recorded by `sim.feedback`) |
| 32 | — | HbA1c booked at `amb_3` |
| 33 | — | furosemide delivered home, then every 30 days |
| 40 | decompensation starts, weight +0.7 kg a day | HbA1c done (LOINC 4548-4, 8.4%) |
| 47 | **readmitted** at `osp_A`, discharged on day 55 | no readmission |

The with-agents branch starts when a `call_task` for `p_00001` executed on any day from 31 to 46 goes through `sim.feedback.apply` (§12); booking comes the next day, delivery 2 days and HbA1c 9 days after the call, and all carry `source = agent_action` and the action id. Before the call both arms are identical (tested).

## 12. Action feedback (step 1.20)

`sim.feedback.apply(run_id, actions)` is how the action service (step 2.12) tells the simulation what it executed on day D, after the simulator's step for D (SPEC §9 tick order). It returns the events that record the actions on day D: `call_task` → `CALL`, `reminder` → `REMINDER`; other types leave no patient event. Effects appear from D + 1 in `Simulator.step`. Until step 2.13 they are a no-op for everyone but Maria, and a test checks that a call or a reschedule changes no simulated event. Step 2.13 adds the effects with their probabilities in the config, which is where AC8 is measured.

The process running a run registers its simulator first: `sim.feedback.register(run_id, sim)`.

## 13. Pattern proof (step 1.21, scope-gate evidence)

`testing/notebooks/patterns.ipynb` simulates the baseline arm of each envelope for a year and reads the run databases only through `engine.db.connect_for_tools`, the connection agent tools get. `sim.pattern_proof.detect` names the places of patterns 1–3 from the data alone; only then is `demo/truth/` opened. Result: **12 of 12 places matched** (3 scenarios × 4 places). `testing/test_patterns.py` runs the same check on 120 days.

| | Scenario 1 | Scenario 2 | Scenario 3 |
|---|---|---|---|
| Echo wait, days 30–40: bottleneck vs others | 45 vs 2 | 39 vs 2 | 37 vs 2 |
| Free echo slots, days 36–56, at the hospital named free | 48 | 67 | 55 |
| Drug collections per patient-year: cooperative vs next lowest | 7.3 vs 11.1 | 7.5 vs 11.1 | 7.4 vs 11.1 |
| Hidden rural comuni found (all found are correct) | 4 of 6 | 3 of 4 | 4 of 4 |
| 30-day readmission, ATS | 12.3% | 12.4% | 12.3% |

Pattern 3 is the weakest signal: the segment (75+, living alone, over 40 km) has only 1–38 telemonitored patients per comune, so a comune needs at least 2 of them to count. If agents miss it in AC1/AC13, the first lever is a larger effect in `scenarios/*.json` (more comuni or a lower `min_age`), not a looser test.

The SQL readmission of SPEC §5.2 (`pattern_proof.readmission_30d`) and the pandas one used for calibration give the same rate (tested).

Maria follows her story, not the pathway file: she is the one place where HF steps are written in code, on purpose. Her comune is Poggio Rusco (§3), while the prototype header says Sermide e Felonica; the console shows the data.
