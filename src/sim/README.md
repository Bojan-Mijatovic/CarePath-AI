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
| 30-day readmission rate | 7.9% | **about 12%: step 1.16 calibrates** |
| Cardiology visit within 30 days of discharge | 78% | |
| Echo within 90 days of discharge | 79% | |
| Mean wait from booking to slot | about 2 days at every facility | no bottleneck in the base table |
| Patients with at least one BNP in the year | 9,976 of 10,000 | |
| Patients sending telemonitoring readings | 3,224 in month 0, 2,581 in month 12 | dropout exceeds new starts; step 1.16 decides whether that is wanted |
| Overbooked slots; events during a hospital stay | 0; 0 | checked |

Behaviour assumptions (`SimParams`, all recalibrated in step 1.16): base admission hazard 0.0008 a day, ×4 for 30 days after a discharge; length of stay 1 + Poisson(7) days; 85% book each post-discharge step, 0–5 days after discharge; 92% attend; a periodic step is booked in the week before it is due, by 85%; 70% start telemonitoring, 1–10 days after discharge; 85% send a reading on a given day, 0.2% drop out a day; a 30-day drug supply, collected after it runs out with a daily chance drawn per patient from Beta(2, 3).

Not yet modelled: deaths, mortality, weight gain before an admission (step 1.16), scenarios (1.17), Maria's script (1.19) and the effect of agents' actions (1.20).
