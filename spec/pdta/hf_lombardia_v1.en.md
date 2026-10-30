# Heart failure care pathway (PDTA) — ATS della Val Padana

> English reference translation of `hf_lombardia_v1.it.md`, the source text. Demo text for the CarePath AI PoC: timings and codes are example values, not clinically validated (delivery plan D28). Pathway model: `spec/pathways/hf_lombardia_v1.json`.

## 1. Patients included

Patients enter the pathway with a heart-failure diagnosis (ICD-9-CM 428.*) or on furosemide (ATC C03CA01).

## 2. Steps after discharge

The pathway starts at every hospital discharge for heart failure (ICD-9-CM 428.*).

1. **Telemonitoring**: activated within 7 days of discharge.
2. **Cardiology visit**: within 30 days of discharge.
3. **Echocardiogram** (code 88.72): within 90 days of discharge.
4. **BNP** (LOINC 30934-4): every 90 days for as long as the patient is on the pathway.

## 3. Monitoring rules

- If the weight recorded by telemonitoring rises by 2 kg or more in 3 days, the cardiology visit is brought forward to within 7 days.
- If the patient has not collected furosemide (ATC C03CA01) for 30 days, an adherence risk is flagged.
- If at one facility the mean wait for an echocardiogram, over the bookings of the last 7 days, exceeds 30 days, an alarm is raised to the ATS.
- If the patients of one MMG group collect the pathway's drugs, over the last 60 days, more than 5 percentage points below the rest of the ATS, an alarm is raised to the ATS.
- If among patients living alone more than 40 km from their reference hospital the share with a telemonitoring reading in the last 7 days, in an area of nearby comuni (within 12 km), is more than 60 percentage points below the rest of the ATS, an alarm is raised to the ATS.

## 4. Patient status on the pathway

- **On track**: everything due by today has been done.
- **Due soon**: a step is due within 7 days and not yet booked.
- **Overdue**: a step is past its deadline and has not been done.
- **Off pathway**: a delay exceeds 30 days, or 2 or more steps are overdue at the same time.

## 5. Actions when a step is late

1. On the day of the delay: automatic reminder to the patient.
2. After 3 days without change: the patient enters the Centro Servizi call list.
3. After 7 days: notice to the general practitioner (MMG).
4. High-risk patients skip the reminder and go straight to the call list.

## 6. Admission

If the doctor decides that a heart-failure admission (ICD-9-CM 428.*) is needed, the ward is cardiology; if no bed is free, internal medicine.

Decisions on diagnosis and therapy always stay with the doctor.
