"""Maria (p_00001): the scripted patient of the demo, the same in every scenario and seed (AC14).

Delivery plan step 1.19; story from Solution Plan §6 and prototype screens 1 and 9b.

Without agents: an HF admission ends with discharge on day 0; telemonitoring from day 6; cardiology visit
on day 24; her furosemide supply ran out on day 0 and she collects nothing, so on day 31 she has gone
30 days without it, and her HbA1c is late; she starts to decompensate on day 40 (weight +0.7 kg a day)
and is readmitted on day 47.

With agents: a Centro Servizi call between day 31 and 46 finds that nobody can bring her the drug
(sim.feedback records the CALL on the call day). From the next day: HbA1c booked, home delivery 2 days
after the call, HbA1c done 9 days after it (days 32, 33 and 40 for a day-31 call); the decompensation never
happens. The effects carry the action id (SPEC §3.1).

Her slots do not use facility capacity, so no scenario can shift her days.
"""

from sim.rng import component_rng

PATIENT_ID = "p_00001"
CALL_OUTCOME = "delivery_arranged"
HOSPITAL, CLINIC = "osp_A", "amb_3"  # her hospital; the nearest clinic, for the HbA1c draw
HF_CODE, DRUG, HBA1C = "428.0", "C03CA01", "4548-4"  # demo codes (delivery plan D28)
ADMITTED, DISCHARGED = -8, 0
LAST_COLLECTION = -30          # 30-day supply, so it runs out on day 0
CARDIO_BOOKED, CARDIO_VISIT, TELEMON_START = 3, 24, 6
DECOMP_START, READMITTED, READMISSION_DISCHARGED = 40, 47, 55
RESCUE_WINDOW = (31, 46)       # a call in these days prevents the readmission
DELIVERY_AFTER, HBA1C_AFTER = 2, 9
BASE_WEIGHT_KG, GAIN_KG_PER_DAY, HBA1C_PERCENT = 71.5, 0.7, 8.4
SUPPLY_DAYS = 30
NOT_SCHEDULED = 10**7  # a day that never comes: keeps the random processes away from her


class MariaScript:
    def __init__(self, first_day: int, days: int):
        self.first_day = first_day
        # Seed-independent noise, so her readings are identical in every run.
        self.noise = 0.3 * component_rng(0, "maria_weight").standard_normal(days - first_day + 400)
        self.call_day: int | None = None
        self.call_action: str | None = None

    def receive_call(self, day: int, action_id: str) -> bool:
        """A Centro Servizi call reached her. Returns whether it changes her path."""
        if self.call_day is None and RESCUE_WINDOW[0] <= day <= RESCUE_WINDOW[1]:
            self.call_day, self.call_action = day, action_id
            return True
        return False

    def _in_hospital(self, day: int, rescued: bool) -> bool:
        return ADMITTED <= day < DISCHARGED or (not rescued and READMITTED <= day < READMISSION_DISCHARGED)

    def events(self, day: int) -> list[tuple]:
        """(event_type, code, value, facility_id, action_id) for one day."""
        rescued = self.call_day is not None and day >= self.call_day
        act = self.call_action
        ev: list[tuple] = []
        if day == ADMITTED or (day == READMITTED and not rescued):
            ev.append(("ADMISSION", HF_CODE, 1.0, HOSPITAL, None))
        if day == DISCHARGED or (day == READMISSION_DISCHARGED and not rescued):
            ev.append(("DISCHARGE", HF_CODE, None, HOSPITAL, None))
        if day <= LAST_COLLECTION and (LAST_COLLECTION - day) % SUPPLY_DAYS == 0:
            ev.append(("DISPENSE", DRUG, float(SUPPLY_DAYS), None, None))
        if day == CARDIO_BOOKED:
            ev.append(("BOOKING", "cardio_visit", float(CARDIO_VISIT), HOSPITAL, None))
        if day == CARDIO_VISIT:
            ev.append(("VISIT", "cardiologia", None, HOSPITAL, None))
        if day == TELEMON_START:
            ev.append(("TELEMON_START", None, None, None, None))
        if self.call_day is not None:
            c = self.call_day
            if day == c + 1:
                ev.append(("BOOKING", "lab", float(c + HBA1C_AFTER), CLINIC, act))
            if day >= c + DELIVERY_AFTER and (day - c - DELIVERY_AFTER) % SUPPLY_DAYS == 0:
                ev.append(("DISPENSE", DRUG, float(SUPPLY_DAYS), None, act))  # home delivery
            if day == c + HBA1C_AFTER:
                ev.append(("LAB", HBA1C, HBA1C_PERCENT, CLINIC, act))
        elif day > READMISSION_DISCHARGED and (day - READMISSION_DISCHARGED - 1) % SUPPLY_DAYS == 0:
            ev.append(("DISPENSE", DRUG, float(SUPPLY_DAYS), None, None))  # collects again after the readmission
        if day >= TELEMON_START and not self._in_hospital(day, rescued):
            gain = GAIN_KG_PER_DAY * (day - DECOMP_START + 1) if not rescued and DECOMP_START <= day < READMITTED else 0.0
            weight = BASE_WEIGHT_KG + gain + self.noise[day - self.first_day]
            ev.append(("TELEMON_READING", None, round(weight, 1), None, None))
        return ev
