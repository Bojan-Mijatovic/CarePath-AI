"""Daily simulator step for one run: events of SPEC §3.1 for every patient, one day at a time.

Delivery plan step 1.15. Structure of arrays: one numpy array per patient attribute, so a day is a few
dozen vectorised operations and no per-patient Python loop (AC2). Every random draw comes from
`component_rng(seed, "<component>:<day>")` and is drawn for all N patients, so two arms of the same seed
see the same random numbers and differ only where their state differs (common random numbers, AC8).

Step timing and capacity come from the pathway JSON and data/capacity.csv; nothing here names a disease
(AC17). Every behaviour probability is in src/sim/config/baseline.json (step 1.16).
Days before 0 are a warm-up whose events are kept as history (SPEC C11).

Outcome model (step 1.16): each day a patient out of hospital may start to decompensate, with a hazard
that rises with days without the drug, overdue pathway steps, distance, living alone and age, and falls
with telemonitoring. Decompensation lasts a few days, during which telemonitored weight rises, and ends in
an admission. That window is where agents can act (step 1.20).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from engine.pathway import Pathway
from sim.rng import component_rng

NO_DAY = -(10**6)
CONFIG_DIR = Path(__file__).resolve().parent / "config"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
EVENT_COLUMNS = ["event_id", "patient_id", "day", "event_type", "code", "value", "facility_id", "asst_id",
                 "mmg_id", "comune_istat", "source", "action_id"]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Risk(Frozen):
    """Log-hazard coefficients of the decompensation hazard."""
    no_drug: float
    drug_grace_days: int
    overdue_step: float
    overdue_window_days: int
    per_10_km: float
    distance_cap_km: float
    lives_alone: float
    telemonitoring: float
    per_10_years_over_75: float


class SimParams(Frozen):
    """Behaviour of synthetic patients; values in src/sim/config/*.json, documented in src/sim/README.md §9."""
    warmup_days: int
    admission_daily: float            # base daily decompensation hazard
    post_discharge_multiplier: float  # hazard multiplier in the days after a discharge
    post_discharge_days: int
    los_mean: float
    discharge_code: str
    decomp_days_min: int
    decomp_days_max: int
    decomp_weight_gain_kg_per_day: float
    risk: Risk
    service_by_step: dict[str, str]   # pathway step id -> service in data/capacity.csv
    p_book: float                     # books a post-discharge step at all
    booking_delay_max: int            # days between discharge and the booking request
    booking_lead_days: int            # the earliest slot is this many days after the request
    max_wait_days: int                # a patient does not book a slot further away than this
    p_attend: float
    periodic_window_days: int         # a periodic step is booked in the week before it is due
    p_book_periodic: float
    p_telemon_start: float
    telemon_start_delay_max: int      # some start after the 7-day deadline
    p_telemon_initial: float          # already on telemonitoring when the warm-up starts
    p_reading: float
    telemon_dropout_daily: float
    supply_days: int
    collect_beta: tuple[float, float]  # daily chance to collect once the supply ran out
    weight_mean_kg: float
    weight_sd_kg: float
    reading_noise_kg: float
    lab_log_mean: float               # lognormal lab value, median about 400
    lab_log_sd: float


def load_params(name: str = "baseline") -> SimParams:
    return SimParams.model_validate_json((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


class CapacityChange(Frozen):
    facility_id: str
    service: str
    slots_per_day: int
    from_day: int


class LowAdherence(Frozen):
    """Pattern 2: patients of one MMG cooperative collect their drug less often."""
    coop_id: str
    collect_multiplier: float


class RuralDropout(Frozen):
    """Pattern 3: older patients living alone far away in a group of comuni leave telemonitoring."""
    comuni: list[str]
    min_age: int
    min_distance_km: float
    dropout_multiplier: float
    start_multiplier: float


class Scenario(Frozen):
    """One envelope (Solution Plan §11): same pattern types as the others, different places."""
    scenario: int
    echo_bottleneck: CapacityChange  # pattern 1: fewer slots at one hospital ...
    echo_free_capacity: CapacityChange  # ... and spare slots at another
    low_adherence: LowAdherence
    rural_dropout: RuralDropout


def load_scenario(n: int) -> Scenario:
    return Scenario.model_validate_json((SCENARIOS_DIR / f"{n}.json").read_text(encoding="utf-8"))


class Simulator:
    def __init__(self, seed: int, patients: pd.DataFrame, ref: dict[str, pd.DataFrame], pathway: Pathway,
                 params: SimParams | None = None, days: int = 365):
        params = params or load_params()
        p, n = params, len(patients)
        self.seed, self.p, self.n, self.pathway = seed, params, n, pathway
        self.first_day = -p.warmup_days
        self.next_event = 1

        # Static patient attributes.
        self.patient_id = patients.patient_id.to_numpy(object)
        self.mmg_id = patients.mmg_id.to_numpy(object)
        self.comune = patients.comune_istat.to_numpy(object)
        self.age = patients.age.to_numpy()
        self.lives_alone = patients.lives_alone.to_numpy(bool)
        self.distance_km = patients.distance_km.to_numpy()
        r = p.risk  # static part of the log hazard
        self.static_risk = (r.per_10_km * np.minimum(patients.distance_km.to_numpy(), r.distance_cap_km) / 10
                            + r.lives_alone * patients.lives_alone.to_numpy()
                            + r.per_10_years_over_75 * np.maximum(patients.age.to_numpy() - 75, 0) / 10)

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
        self.last_done = {s.id: np.full(n, NO_DAY) for s in self.post_steps}  # for overdue post-discharge steps
        self.decomp_start = np.full(n, NO_DAY)
        self.decomp_admit = np.full(n, NO_DAY)
        self.next_due = {s.id: self.first_day + p.periodic_window_days + (rng.random(n) * s.every_days).astype(int)
                         for s in self.periodic_steps}
        self.telemon_on = np.zeros(n, bool)
        self.telemon_on[:] = rng.random(n) < p.p_telemon_initial
        self.telemon_start_on = np.full(n, NO_DAY)
        self.supply_end = self.first_day + (rng.random(n) * p.supply_days).astype(int)
        self.collect_q = rng.beta(*p.collect_beta, n)
        self.base_weight = np.clip(rng.normal(p.weight_mean_kg, p.weight_sd_kg, n), 45, 140)
        self.telemon_start_p = np.full(n, p.p_telemon_start)
        self.telemon_dropout_p = np.full(n, p.telemon_dropout_daily)

    def apply_scenario(self, scenario: Scenario, mmg: pd.DataFrame) -> None:
        """Inject the three patterns of one envelope (step 1.17). Call before the warm-up."""
        for change in (scenario.echo_bottleneck, scenario.echo_free_capacity):
            r = np.flatnonzero((self.fac_id[self.res_fac] == change.facility_id) & (self.res_service == change.service))
            if len(r) != 1:
                raise ValueError(f"no capacity row for {change.facility_id} {change.service}")
            self.cap[r[0], max(change.from_day - self.first_day, 0):] = change.slots_per_day
        low = scenario.low_adherence
        coop = pd.Series(self.mmg_id).map(mmg.set_index("mmg_id").coop_id).to_numpy()
        if not (coop == low.coop_id).any():
            raise ValueError(f"{low.coop_id} has no patients")
        self.collect_q[coop == low.coop_id] *= low.collect_multiplier
        rural = scenario.rural_dropout
        hit = (np.isin(self.comune, rural.comuni) & (self.age >= rural.min_age) & self.lives_alone
               & (self.distance_km > rural.min_distance_km))
        self.telemon_dropout_p[hit] *= rural.dropout_multiplier
        self.telemon_start_p[hit] *= rural.start_multiplier

    def _u(self, component: str, day: int) -> np.ndarray:
        return component_rng(self.seed, f"{component}:{day}").random(self.n)

    def hazard(self, day: int) -> np.ndarray:
        """Daily decompensation hazard of every patient (outcome model, step 1.16)."""
        p, r = self.p, self.p.risk
        since = day - self.last_discharge
        overdue = np.zeros(self.n, bool)
        for s in self.post_steps:
            overdue |= ((since > s.due_days) & (since <= r.overdue_window_days)
                        & (self.last_done[s.id] < self.last_discharge))
        log_risk = (self.static_risk
                    + r.no_drug * (day > self.supply_end + r.drug_grace_days)
                    + r.overdue_step * overdue
                    + r.telemonitoring * self.telemon_on)
        recent = since <= p.post_discharge_days
        return p.admission_daily * np.where(recent, p.post_discharge_multiplier, 1.0) * np.exp(log_risk)

    def _book(self, day: int, res: np.ndarray) -> np.ndarray:
        """First free slot from day + lead for each request, in patient order; NO_DAY when the first free
        slot is more than max_wait_days away (the patient gives up). Updates `booked`."""
        slots = np.full(len(res), NO_DAY)
        start = day + self.p.booking_lead_days - self.first_day
        last = day + self.p.max_wait_days - self.first_day
        for r in np.unique(res):
            sel = np.flatnonzero(res == r)
            free = np.clip(self.cap[r, start:last + 1] - self.booked[r, start:last + 1], 0, None)
            pos = np.searchsorted(np.cumsum(free), np.arange(1, len(sel) + 1))
            ok = pos < len(free)
            np.add.at(self.booked[r], start + pos[ok], 1)
            slots[sel[ok]] = start + pos[ok] + self.first_day
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
                self.last_done[s.id][out[self.telemon_on[out]]] = day  # already on telemonitoring
                go = out[(self._u(f"tel_start:{s.id}", day)[out] < self.telemon_start_p[out]) & ~self.telemon_on[out]]
                delay = self._u(f"tel_delay:{s.id}", day)[go]
                self.telemon_start_on[go] = day + 1 + (delay * p.telemon_start_delay_max).astype(int)
            for s in self.cap_steps:
                if s not in self.post_steps:
                    continue
                go = out[self._u(f"book:{s.id}", day)[out] < p.p_book]
                self.book_on[s.id][go] = day + (self._u(f"book_delay:{s.id}", day)[go] * (p.booking_delay_max + 1)).astype(int)

        # 2. Admissions: decompensations that reach hospital today, then new decompensations.
        adm = np.flatnonzero((self.decomp_admit == day) & ~self.in_hosp)
        los = 1 + component_rng(self.seed, f"los:{day}").poisson(p.los_mean - 1, n)
        self.in_hosp[adm] = True
        self.discharge_day[adm] = day + los[adm]
        self.decomp_start[adm] = self.decomp_admit[adm] = NO_DAY
        emit(adm, "ADMISSION", p.discharge_code, np.ones(len(adm)), self.ref_fac[adm])
        free = ~self.in_hosp & (self.decomp_admit == NO_DAY) & (self.last_discharge != day)
        new = np.flatnonzero(free & (self._u("decomp", day) < self.hazard(day)))
        span = p.decomp_days_max - p.decomp_days_min + 1
        self.decomp_start[new] = day
        self.decomp_admit[new] = day + p.decomp_days_min + (self._u("decomp_days", day)[new] * span).astype(int)

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
                self.book_on[s.id][idx] = NO_DAY
                ok = slots != NO_DAY
                self.appt_day[s.id][idx[ok]] = slots[ok]
                if s.every_days:
                    self.next_due[s.id][idx[~ok]] += s.every_days  # gave up on this cycle
                emit(idx[ok], "BOOKING", self.res_service[res[ok]], slots[ok].astype(float), self.res_fac[res[ok]])

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
            if s.id in self.last_done:
                self.last_done[s.id][came] = day
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
        for s in self.telemon_steps:
            self.last_done[s.id][started] = day
        emit(started, "TELEMON_START")
        reading = np.flatnonzero(self.telemon_on & ~self.in_hosp & (self._u("reading", day) < p.p_reading))
        noise = component_rng(self.seed, f"weight:{day}").standard_normal(n)
        gain = np.where(self.decomp_start > NO_DAY, (day - self.decomp_start + 1) * p.decomp_weight_gain_kg_per_day, 0.0)
        weight = self.base_weight + gain + p.reading_noise_kg * noise
        emit(reading, "TELEMON_READING", None, np.round(weight[reading], 1))
        self.telemon_on &= ~(self._u("dropout", day) < self.telemon_dropout_p)

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
