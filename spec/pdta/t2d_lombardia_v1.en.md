# Type 2 diabetes care pathway (PDTA) — ATS della Val Padana (draft)

> English reference translation of `t2d_lombardia_v1.it.md`, the source text. **Draft** for option B of the CarePath AI PoC (delivery plan, phase 3). Demo text: timings and codes are example values, not clinically validated (delivery plan D28). The Pathway Builder produces the pathway model from this text.

## 1. Patients included

Patients enter the pathway with a diabetes diagnosis (ICD-9-CM 250.*) or on metformin (ATC A10BA02).

## 2. Pathway steps

The pathway starts when the patient is enrolled.

1. **Glycated haemoglobin HbA1c** (LOINC 4548-4): every 180 days.
2. **Kidney function, eGFR** (LOINC 33914-3): every 365 days.
3. **Diabetology visit**: every 365 days.
4. **Eye fundus examination** (code 95.02): every 365 days.

## 3. Monitoring rules

- If the patient has not collected metformin (ATC A10BA02) for 60 days, an adherence risk is flagged.
- If HbA1c is more than 30 days overdue, a missing HbA1c measurement is flagged.

## 4. Patient status on the pathway

- **On track**: everything due by today has been done.
- **Due soon**: a step is due within 14 days and not yet booked.
- **Overdue**: a step is past its deadline and has not been done.
- **Off pathway**: a delay exceeds 90 days, or 2 or more steps are overdue at the same time.

## 5. Actions when a step is late

1. On the day of the delay: automatic reminder to the patient.
2. After 7 days without change: the patient enters the Centro Servizi call list.
3. After 14 days: notice to the general practitioner (MMG).
4. High-risk patients skip the reminder and go straight to the call list.

## 6. Admission

If the doctor decides that an admission for diabetes with complications (ICD-9-CM 250.*) is needed, the ward is internal medicine; alternatively endocrinology.

Decisions on diagnosis and therapy always stay with the doctor.
