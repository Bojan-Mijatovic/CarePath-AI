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
| `osp_A` Ospedale A | Mantova | Mantova | 6 | 3 | 38 |
| `osp_B` Ospedale B | Cremona | Cremona | 3 | 1 | 19 |
| `osp_C` Ospedale C | Crema | Crema | 3 | 2 | 15 |
| `amb_1` Poliambulatorio 1 | Mantova | Castiglione delle Stiviere | — | 1 | 12 |
| `amb_2` Poliambulatorio 2 | Mantova | Viadana | — | 1 | 12 |
| `amb_3` Poliambulatorio 3 | Mantova | Suzzara | — | 1 | 12 |
| `amb_4` Poliambulatorio 4 | Cremona | Casalmaggiore | — | 1 | 9 |
| `amb_5` Poliambulatorio 5 | Cremona | Soresina | — | 1 | 9 |
| `amb_6` Poliambulatorio 6 | Crema | Rivolta d'Adda | — | 1 | 14 |

Slots per simulated day; the PoC has no weekly cycle. Only hospitals do echo, so pattern 1 is a hospital-to-hospital comparison. No facility is in the Oltrepò, which keeps Maria's area far from services (pattern 3).

How the slots were sized. All of these are assumptions, which `testing/test_sim_facilities.py` checks and step 1.16 recalibrates:

- Patients per ASST in proportion to the population aged 65+: 52.7% Mantova, 26.5% Cremona, 20.9% Crema.
- 0.33 HF discharges per patient per year, including readmissions. Each discharge needs one echo (due in 90 days) and one cardiology visit (due in 30 days), as in the pathway of SPEC §4. That gives 4.76, 2.39 and 1.89 per day.
- A BNP test every 90 days for every patient: 58.5, 29.4 and 23.2 per day.
- Capacity is at least 1.25 × demand for every ASST and service. The base table has no bottleneck; each scenario creates one (step 1.17), for example by cutting `osp_B` echo from 3 to 1 slot a day while `osp_C` keeps spare slots.

**Maria's comune:** a rural comune in the Oltrepò Mantovano, about 45 km by road from `osp_A`. Candidates, all in `asst_mantova`: Poggio Rusco (020042, 6,535 residents), Ostiglia (020038, 6,739), Sermide e Felonica (020061, 7,018). Step 1.13 picks the one whose computed distance is closest to 45 km.

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
