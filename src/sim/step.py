"""Daily simulator step for one run: events of SPEC §3.1 for every patient, one day at a time.

Delivery plan step 1.15. Structure of arrays: one numpy array per patient attribute, so a day is a few
dozen vectorised operations and no per-patient Python loop (AC2). Every random draw comes from
`component_rng(seed, "<component>:<day>")` and is drawn for all N patients, so two arms of the same seed
see the same random numbers and differ only where their state differs (common random numbers, AC8).

Step timing and capacity come from the pathway JSON and data/capacity.csv; nothing here names a disease
(AC17). The behaviour probabilities in SimParams are assumptions that step 1.16 calibrates.
Days before 0 are a warm-up whose events are kept as history (SPEC C11).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.pathway import Pathway
from sim.rng import component_rng

NO_DAY = -(10**6)
EVENT_COLUMNS = ["event_id", "patient_id", "day", "event_type", "code", "value", "facility_id", "asst_id",
                 "mmg_id", "comune_istat", "source", "action_id"]


@dataclass(frozen=True)
class SimParams:
    """Behaviour of synthetic patients. Every value is an assumption (src/sim/README.md §8)."""
    warmup_days: int = 120
    # Admissions: a base daily hazard, raised for 30 days after a discharge (readmissions).
    admission_daily: float = 0.0008
    post_discharge_multiplier: float = 4.0
    post_discharge_days: int = 30
    los_mean: float = 8.0
    discharge_code: str = "428.0"
    # Pathway steps with capacity: pathway step id -> service in data/capacity.csv.
    service_by_step: dict[str, str] = field(default_factory=lambda: {
        "cardio_visit": "cardio_visit", "echo": "echo", "lab_bnp": "lab"})
    p_book: float = 0.85          # books a post-discharge step at all
    booking_delay_max: int = 5    # days between discharge and the booking request
    booking_lead_days: int = 2    # the earliest slot is this many days after the request
    p_attend: float = 0.92
    periodic_window_days: int = 7  # a periodic step is booked in the week before it is due
    p_book_periodic: float = 0.85
    p_telemon_start: float = 0.70
    telemon_start_delay_max: int = 10  # some start after the 7-day deadline
    p_telemon_initial: float = 0.35    # already on telemonitoring when the warm-up starts
    p_reading: float = 0.85
    telemon_dropout_daily: float = 0.002
    supply_days: int = 30
    collect_beta: tuple[float, float] = (2.0, 3.0)  # daily chance to collect once the supply ran out
    weight_mean_kg: float = 78.0
    weight_sd_kg: float = 12.0
    reading_noise_kg: float = 0.4
    lab_log_mean: float = 6.0  # lognormal lab value, median about 400
    lab_log_sd: float = 0.6


class Simulator:
    def __init__(self, seed: int, patients: pd.DataFrame, ref: dict[str, pd.DataFrame], pathway: Pathway,
                 params: SimParams = SimParams(), days: int = 365):
        p, n = params, len(patients)
        self.seed, self.p, self.n, self.pathway = seed, params, n, pathway
        self.first_day = -p.warmup_days
        self.next_event = 1

        # Static patient attributes.
        self.patient_id = patients.patient_id.to_numpy(object)
        self.mmg_id = patients.mmg_id.to_numpy(object)
        self.comune = patients.comune_istat.to_numpy(object)

        # Facilities and capacity resources (facility × service).
        fac = ref["facilities"].reset_index(drop=True)
        self.fac_id = fac.facility_id.to_numpy(object)
        self.fac_asst = fac.asst_id.to_numpy(object)
        fac_index = {f: i for i, f in enumerate(self.fac_id)}
        cap = ref["capacity"].reset_index(drop=True)
        self.res_fac = cap.facility_id.map(fac_index).to_numpy()
        self.res_service = cap.service.to_numpy(object)
        horizon = p.warmup_days + days + 400
        self.cap = np.repeat(cap.slots_per_day.to_numpy()[:, None], horizon, axis=1)  # scenarios edit this
        self.booked = np.zeros_like(self.cap)
        self.ref_fac = patients.ref_facility_id.map(fac_index).to_numpy()

        # Pathway structure: the anchor (discharge), steps due after it, and periodic steps.
        anchor = next(s for s in pathway.steps if s.event == "DISCHARGE")
        self.post_steps = [s for s in pathway.steps if s.after == anchor.id]
        self.periodic_steps = [s for s in pathway.steps if s.every_days]
        self.drug_atc = pathway.eligibility.any_drug_atc[0]
        cap_steps = [s for s in self.post_steps + self.periodic_steps if s.id in p.service_by_step]
        self.telemon_steps = [s for s in self.post_steps if s.event == "TELEMON_START"]

        # Each patient uses the nearest facility of their own ASST that offers the service.
        dist = ref["distances"].pivot(index="comune_istat", columns="facility_id", values="distance_km")[self.fac_id]
        d = dist.loc[self.comune].to_numpy()
        same_asst = self.fac_asst[None, :] == patients.asst_id.to_numpy(object)[:, None]
        self.step_res: dict[str, np.ndarray] = {}
        for s in cap_steps:
            service = p.service_by_step[s.id]
            res_of_fac = np.full(len(self.fac_id), -1)
            for r in np.flatnonzero(self.res_service == service):
                res_of_fac[self.res_fac[r]] = r
            masked = np.where(same_asst & (res_of_fac >= 0)[None, :], d, np.inf)
            self.step_res[s.id] = res_of_fac[masked.argmin(axis=1)]
        self.cap_steps = cap_steps

        # Dynamic state.
        rng = component_rng(seed, "init")
        self.in_hosp = np.zeros(n, bool)
        self.discharge_day = np.full(n, NO_DAY)
        self.last_discharge = np.full(n, NO_DAY)
        self.book_on = {s.id: np.full(n, NO_DAY) for s in cap_steps}
        self.appt_day = {s.id: np.full(n, NO_DAY) for s in cap_steps}
        self.next_due = {s.id: self.first_day + p.periodic_window_days + (rng.random(n) * s.every_days).astype(int)
                         for s in self.periodic_steps}
        self.telemon_on = np.zeros(n, bool)
        self.telemon_on[:] = rng.random(n) < p.p_telemon_initial
        self.telemon_start_on = np.full(n, NO_DAY)
        self.supply_end = self.first_day + (rng.random(n) * p.supply_days).astype(int)
        self.collect_q = rng.beta(*p.collect_beta, n)
        self.base_weight = np.clip(rng.normal(p.weight_mean_kg, p.weight_sd_kg, n), 45, 140)

    def _u(self, component: str, day: int) -> np.ndarray:
        return component_rng(self.seed, f"{component}:{day}").random(self.n)

    def _book(self, day: int, res: np.ndarray) -> np.ndarray:
        """First free slot from day + lead for each request, in patient order. Updates `booked`."""
        slots = np.empty(len(res), int)
        start = day + self.p.booking_lead_days - self.first_day
        for r in np.unique(res):
            sel = np.flatnonzero(res == r)
            free = np.clip(self.cap[r, start:] - self.booked[r, start:], 0, None)
            pos = np.searchsorted(np.cumsum(free), np.arange(1, len(sel) + 1))
            if pos[-1] >= len(free):
                raise RuntimeError(f"booking horizon too short for resource {r}")
            np.add.at(self.booked[r], start + pos, 1)
            slots[sel] = start + pos + self.first_day
        return slots

    def step(self, day: int) -> pd.DataFrame:
        """Advance one simulated day and return its events (SPEC §3.1)."""
        p, n = self.p, self.n
        chunks: list[tuple] = []

        def emit(idx, event_type, code=None, value=None, fac=None):
            if len(idx):
                chunks.append((idx, event_type, code, value, fac))

        # 1. Discharges, then the post-discharge steps they open.
        out = np.flatnonzero(self.in_hosp & (self.discharge_day == day))
        self.in_hosp[out] = False
        self.last_discharge[out] = day
        emit(out, "DISCHARGE", p.discharge_code, None, self.ref_fac[out])
        if len(out):
            for s in self.telemon_steps:
                go = out[(self._u(f"tel_start:{s.id}", day)[out] < p.p_telemon_start) & ~self.telemon_on[out]]
                delay = self._u(f"tel_delay:{s.id}", day)[go]
                self.telemon_start_on[go] = day + 1 + (delay * p.telemon_start_delay_max).astype(int)
            for s in self.cap_steps:
                if s not in self.post_steps:
                    continue
                go = out[self._u(f"book:{s.id}", day)[out] < p.p_book]
                self.book_on[s.id][go] = day + (self._u(f"book_delay:{s.id}", day)[go] * (p.booking_delay_max + 1)).astype(int)

        # 2. Admissions: base hazard, higher in the 30 days after a discharge.
        recent = (day - self.last_discharge) <= p.post_discharge_days
        hazard = p.admission_daily * np.where(recent, p.post_discharge_multiplier, 1.0)
        adm = np.flatnonzero(~self.in_hosp & (self.last_discharge != day) & (self._u("admission", day) < hazard))
        los = 1 + component_rng(self.seed, f"los:{day}").poisson(p.los_mean - 1, n)
        self.in_hosp[adm] = True
        self.discharge_day[adm] = day + los[adm]
        emit(adm, "ADMISSION", p.discharge_code, np.ones(len(adm)), self.ref_fac[adm])

        # 3. Periodic steps open their booking window in the week before they are due.
        for s in self.periodic_steps:
            opening = np.flatnonzero(self.next_due[s.id] - p.periodic_window_days == day)
            will = self._u(f"book:{s.id}", day)[opening] < p.p_book_periodic
            go = opening[will]
            self.book_on[s.id][go] = day + (self._u(f"book_delay:{s.id}", day)[go] * (p.periodic_window_days + 1)).astype(int)
            self.next_due[s.id][opening[~will]] += s.every_days  # skipped this cycle

        # 4. Booking requests: patients in hospital ask again the day after discharge.
        for s in self.cap_steps:
            req = self.book_on[s.id] == day
            later = req & self.in_hosp
            self.book_on[s.id][later] = self.discharge_day[later] + 1
            idx = np.flatnonzero(req & ~self.in_hosp)
            if len(idx):
                res = self.step_res[s.id][idx]
                slots = self._book(day, res)
                self.appt_day[s.id][idx] = slots
                self.book_on[s.id][idx] = NO_DAY
                emit(idx, "BOOKING", self.res_service[res], slots.astype(float), self.res_fac[res])

        # 5. Appointments due today.
        for s in self.cap_steps:
            today = np.flatnonzero(self.appt_day[s.id] == day)
            self.appt_day[s.id][today] = NO_DAY
            came = today[~self.in_hosp[today] & (self._u(f"attend:{s.id}", day)[today] < p.p_attend)]
            fac = self.res_fac[self.step_res[s.id][came]]
            if s.event == "LAB":
                v = np.exp(p.lab_log_mean + p.lab_log_sd * component_rng(self.seed, f"labval:{day}").standard_normal(n))
                emit(came, "LAB", (s.loinc or [None])[0], np.round(v[came]), fac)
            else:
                emit(came, s.event, s.specialty or (s.codes or [None])[0], None, fac)
            if s.every_days:
                self.next_due[s.id][came] = day + s.every_days
                missed = np.setdiff1d(today, came, assume_unique=True)
                self.next_due[s.id][missed] += s.every_days

        # 6. Telemonitoring: start, daily readings, dropout.
        start = self.telemon_start_on == day
        later = start & self.in_hosp
        self.telemon_start_on[later] = self.discharge_day[later] + 1
        started = np.flatnonzero(start & ~self.in_hosp)
        self.telemon_on[started] = True
        self.telemon_start_on[started] = NO_DAY
        emit(started, "TELEMON_START")
        reading = np.flatnonzero(self.telemon_on & ~self.in_hosp & (self._u("reading", day) < p.p_reading))
        noise = component_rng(self.seed, f"weight:{day}").standard_normal(n)
        emit(reading, "TELEMON_READING", None, np.round(self.base_weight[reading] + p.reading_noise_kg * noise[reading], 1))
        self.telemon_on &= ~(self._u("dropout", day) < p.telemon_dropout_daily)

        # 7. Pharmacy: once the supply has run out, a patient collects with their own daily chance.
        coll = np.flatnonzero(~self.in_hosp & (day >= self.supply_end) & (self._u("collect", day) < self.collect_q))
        self.supply_end[coll] = day + p.supply_days
        emit(coll, "DISPENSE", self.drug_atc, np.full(len(coll), float(p.supply_days)))

        return self._frame(day, chunks)

    def _frame(self, day: int, chunks: list[tuple]) -> pd.DataFrame:
        if not chunks:
            return pd.DataFrame(columns=EVENT_COLUMNS)
        idx = np.concatenate([c[0] for c in chunks])
        k = len(idx)
        etype = np.concatenate([np.full(len(c[0]), c[1], object) for c in chunks])
        code = np.concatenate([c[2] if isinstance(c[2], np.ndarray) else np.full(len(c[0]), c[2], object)
                               for c in chunks])
        value = np.concatenate([np.full(len(c[0]), np.nan) if c[3] is None else np.asarray(c[3], float)
                                for c in chunks])
        fac = np.concatenate([np.full(len(c[0]), -1) if c[4] is None else c[4] for c in chunks])
        has_fac = fac >= 0
        ids = np.arange(self.next_event, self.next_event + k)
        self.next_event += k
        return pd.DataFrame({
            "event_id": ["ev_" + str(i) for i in ids],
            "patient_id": self.patient_id[idx],
            "day": np.full(k, day, np.int32),
            "event_type": etype,
            "code": code,
            "value": value,
            "facility_id": np.where(has_fac, self.fac_id[np.maximum(fac, 0)], None),
            "asst_id": np.where(has_fac, self.fac_asst[np.maximum(fac, 0)], None),
            "mmg_id": self.mmg_id[idx],
            "comune_istat": self.comune[idx],
            "source": "sim",
            "action_id": None,
        })

    def warm_up(self) -> list[pd.DataFrame]:
        return [self.step(d) for d in range(self.first_day, 0)]

    def capacity_slots(self) -> pd.DataFrame:
        """SPEC §3.2 `capacity_slots` over the whole horizon, warm-up included."""
        r, d = (a.ravel() for a in np.indices(self.cap.shape))
        return pd.DataFrame({
            "facility_id": self.fac_id[self.res_fac[r]],
            "service": self.res_service[r],
            "day": (d + self.first_day).astype(np.int32),
            "slots_total": self.cap.ravel(),
            "slots_booked": self.booked.ravel(),
        })
