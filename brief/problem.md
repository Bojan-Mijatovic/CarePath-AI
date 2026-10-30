# Problem brief

Owner: R5. Delivery plan step 0.11. Last updated: 28 Oct 2026. Source: [Solution Plan](../docs/CarePath-AI-Solution-Plan.pdf) §2–§4 and §17.

## 1. The problem in one sentence

Every chronic patient in Lombardy's care programme has an individual care plan (PAI), but nobody checks every day whether it is being followed, so deviations surface only when the patient is back in hospital.

> "Ogni paziente cronico ha un PAI. Ma chi verifica, ogni giorno, che venga eseguito?"

**Workshop framing.** The workshop asks for a problem from the participants' own work. Ours: teams that deliver systems to regional health services have no way to show where patients get lost along the care pathway, why, and what it costs.

## 2. Context

- Lombardy runs its health system through 8 ATS (planning, purchasing, control) and 27 ASST (hospitals and outpatient services).
- Since July 2024, the chronic-care programme (PIC) puts the GP (MMG) at the centre: the MMG enrols patients and writes the PAI. An MMG receives €8 per patient after enrolling at least 15% of their chronic patients.
- A PAI is valid for one year and is published in the patient's electronic health record (FSE). The services in it are organised by the MMG cooperatives' Centro Servizi or by the ASST/COT.
- The national outcomes programme (PNE, run by Agenas) publishes 30-day readmission after heart failure for every hospital. Italy's crude rate was 11.87% in 2024 (PNE 2025).
- PoC territory: ATS della Val Padana, with ASST Mantova, Cremona and Crema. It has 177 comuni and 761,667 residents, 25.1% of them aged 65 or more (ISTAT, 1 Jan 2025; [src/sim/README.md](../src/sim/README.md)).

## 3. What "off plan" means

A PAI says what must happen and by when: for example a cardiology visit within 30 days of discharge, an echo within 3 months, the drug collected every month, telemonitoring readings every day. A patient is **off plan** when something that was due by today has not happened.

| Status | Meaning |
|---|---|
| On track (*in linea*) | everything due by today is done |
| Due soon (*scadenza vicina*) | a step is due soon and not booked |
| Overdue (*in ritardo*) | a step is past its deadline and not done |
| Dropped (*fuori percorso*) | overdue for a long time, or several steps overdue at once |

Five kinds of deviation:

1. **Missed visit or exam.** The deadline has passed and nothing is in the record.
2. **Drug not collected.** The pharmacy has not dispensed a chronic drug for longer than allowed.
3. **Missing lab test.** For example HbA1c or BNP not done on time.
4. **Telemonitoring stopped.** No readings for several days.
5. **Wait too long.** An appointment exists, but after the deadline, because the hospital has no capacity.

Deviations 1–4 usually come from the patient's situation (forgot, lives alone, lives far away). Deviation 5 comes from the system. The response depends on the cause: a reminder or a call for the first kind, an earlier slot at another facility for the second.

**Example.** On day 31, Maria has not collected furosemide for 30 days and her HbA1c is late. She is off plan in two places. A call that same day finds that nobody can bring her the drug. Centro Servizi arranges delivery and books the test, and she is not readmitted on day 47.

## 4. Users and what each one needs

| User | Need | What CarePath gives them |
|---|---|---|
| ATS manager (the buyer) | where the chronic-care programme fails and what to fund | console, investigations, what-if, PNE forecast, choice of the next disease, audit and undo of every action |
| Centro Servizi / COT | whom to call today and why | daily call list, action queue |
| MMG | which patients the AI enrolled and who is late | notices about patients the AI enrolled, rescheduled or admitted |
| Clinical board | whether the PDTA works in practice | notices about activated pathway models, improvement proposals with evidence |
| Hospital (emergency, bed manager) | where to admit a patient | a bed assigned in seconds, occupancy per ward in every hospital (optional layer) |

## 5. Pains today

1. Data is spread across the FSE, hospitals, labs and pharmacies; nobody sees the whole patient path.
2. Deviations from the PAI are found late, usually only after a readmission.
3. Nobody knows why a patient drops out: the patient or the system.
4. Patients wait weeks for exams while another hospital in the same ATS has free slots.
5. Many chronic patients who should be enrolled are not.
6. Putting a new PDTA into practice takes months.
7. When an admission is needed, a free bed is found by phoning ward after ward.
8. Capacity and investment decisions are made without simulating their effect.
9. The effect of interventions is not measured, so nobody knows what is worth funding.

## 6. Success metrics (PoC, on simulated data)

Every metric is computed by code from the simulation and compared with and without agents on the same seed.

| Metric | How it is measured | Target or criterion |
|---|---|---|
| Share of patients following their PAI on time | `kpi_daily.on_track_pct` | higher with agents |
| 30-day readmissions (PNE-style definition) | `kpi_daily.readmission_rate_30d` | baseline calibrated to about 12% (10–16% per hospital); fewer with agents (AC8) |
| Time from deviation to action | audit log | same simulated day for automatic actions |
| Euros saved from avoided readmissions | readmissions × cost per readmission (SPEC Q2) | shown on Confronto and in what-if |
| Waiting time per ASST before and after automatic rescheduling | `wait_by_hospital` | lower at the bottleneck hospital |
| Patients the AI enrolled, against the MMG's 15% target | audit log, option B | AC15: at least 90% of candidates |
| Time from PDTA text to active pathway model | timer, option B | AC16: under 60 s |
| Time from admission request to assigned bed | timer, optional layer | AC18: under 3 s |

The euro figures and the effect of each intervention rest on probabilities the team sets in the simulator config. The demo says so at the start (D24), and the limitations list every such assumption.

## 7. Scope

**In scope:** heart failure for 10,000 synthetic patients in ATS Val Padana with 3 scenarios and Maria. Option B adds type 2 diabetes (about 3,000 patients), including the Pathway Builder (D23). Optional agents and Bed Finder are added only if their gates pass (delivery plan §8).

**Out of scope** (the "Gde ovo može da ide" slide): real FSE 2.0 integration, a data-mapping agent, outcome learning and causal analysis, phenotyping, NLP on discharge letters, a third disease (BPCO), and federated analysis across several ATS.

**Not proved by the PoC:** work on real data and integrations, clinical validation, and the real effect of interventions. In the simulation these are assumptions.

**Tuned to the scenarios:** the alarm that finds pattern 3 (patients living alone far away who leave telemonitoring) uses a 12 km area, a 5-patient minimum and a 60-point threshold chosen on the same three scenarios it is tested on, and its 40 km segment is the simulator's own threshold for the pattern (delivery plan D47). On real data it would need its own calibration.
