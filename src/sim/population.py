"""Synthetic heart-failure population of ATS Val Padana: patients, their MMG and MMG cooperatives.

Delivery plan step 1.14; contracts in spec/SPEC.md §3.2 (`patients`, `mmg`). Reads the reference data
of steps 1.10–1.13 in src/sim/data/. Every number below marked "assumption" is listed in
src/sim/README.md §7 and is recalibrated in step 1.16.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sim.reference_data import DATA_DIR
from sim.rng import component_rng

N_HF_PATIENTS = 10_000
ADULTS_PER_MMG = 1_300  # assumption; the Lombardy ceiling is 1,500 patients per MMG
MIN_AGE_MMG = 15        # younger patients have a paediatrician; 15 is the nearest ISTAT band edge
MMG_PER_COOP = 30       # assumption: cooperative size

# Assumption: HF prevalence by 5-year band start, a smooth rise with age, used only as relative
# sampling weights. Steps shared by two bands would put artificial jumps in the age pyramid.
HF_PREVALENCE = {45: 0.004, 50: 0.006, 55: 0.010, 60: 0.015, 65: 0.025, 70: 0.040, 75: 0.060, 80: 0.090,
                 85: 0.120, 90: 0.150, 95: 0.150, 100: 0.150}
# Assumption: probability of living alone by band start (lower bound) and sex.
LIVES_ALONE = [(0, {"F": 0.15, "M": 0.15}), (65, {"F": 0.30, "M": 0.15}), (75, {"F": 0.45, "M": 0.20}),
               (85, {"F": 0.55, "M": 0.30})]

PATIENT_COLUMNS = ["patient_id", "sex", "age", "comune_istat", "asst_id", "mmg_id", "lives_alone",
                   "ref_facility_id", "distance_km", "conditions"]


@dataclass(frozen=True)
class Maria:
    """The demo patient, identical in every scenario (SPEC C6, Solution Plan §6)."""
    patient_id: str = "p_00001"
    sex: str = "F"
    age: int = 81
    comune_istat: str = "020042"  # Poggio Rusco, src/sim/README.md §3
    lives_alone: bool = True
    conditions: tuple[str, ...] = ("HF", "T2D")


def load_reference() -> dict[str, pd.DataFrame]:
    read = lambda name: pd.read_csv(DATA_DIR / f"{name}.csv", dtype={"comune_istat": str})
    return {name: read(name) for name in ("comuni", "population_by_age", "facilities", "distances")}


def build_mmg(comuni: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """MMG per comune in proportion to adults (at least one), grouped into cooperatives of neighbouring
    comuni inside each ASST. Deterministic: no random draws."""
    adults = population[population.age_from >= MIN_AGE_MMG].groupby("comune_istat").population.sum()
    per_comune = comuni.assign(n_mmg=comuni.comune_istat.map(adults).div(ADULTS_PER_MMG).round().clip(lower=1)
                               .astype(int))
    rows, coop = [], 0
    for _, asst in per_comune.sort_values(["asst_id", "lon", "lat"]).groupby("asst_id", sort=True):
        # Walk the ASST west to east and cut a new cooperative once the current one is full. Comuni stay
        # whole, and a short remainder joins the last cooperative instead of forming a tiny one.
        groups, size = [], 0
        for c in asst.itertuples():
            if not groups or size >= MMG_PER_COOP:
                groups.append([])
                size = 0
            groups[-1].append(c)
            size += c.n_mmg
        if len(groups) > 1 and size < MMG_PER_COOP / 2:
            groups[-2].extend(groups.pop())
        for group in groups:
            coop += 1
            rows += [(c.comune_istat, f"coop_{coop}") for c in group for _ in range(c.n_mmg)]
    mmg = pd.DataFrame(rows, columns=["comune_istat", "coop_id"])
    mmg.insert(0, "mmg_id", [f"mmg_{i:03d}" for i in range(1, len(mmg) + 1)])
    mmg["cs_id"] = mmg.coop_id.str.replace("coop_", "cs_")  # one Centro Servizi per cooperative
    return mmg[["mmg_id", "coop_id", "cs_id", "comune_istat"]]


def lives_alone_probability(age: np.ndarray, sex: np.ndarray) -> np.ndarray:
    p = np.zeros(len(age))
    for start, by_sex in LIVES_ALONE:
        for s, value in by_sex.items():
            p[(age >= start) & (sex == s)] = value
    return p


def generate_patients(seed: int, ref: dict[str, pd.DataFrame] | None = None,
                      n: int = N_HF_PATIENTS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(patients, mmg) for one seed. Maria is p_00001; the other n − 1 are sampled."""
    ref = ref or load_reference()
    comuni, facilities = ref["comuni"].set_index("comune_istat"), ref["facilities"]
    mmg = build_mmg(ref["comuni"], ref["population_by_age"])
    rng = component_rng(seed, "population")

    cells = ref["population_by_age"]
    cells = cells[cells.age_from.isin(HF_PREVALENCE)].reset_index(drop=True)
    weights = (cells.population * cells.age_from.map(HF_PREVALENCE)).to_numpy(float)
    picked = cells.iloc[rng.choice(len(cells), size=n - 1, p=weights / weights.sum())]
    width = np.where(picked.age_to.isna(), 1, 5)  # 100 and over counts as age 100
    age = picked.age_from.to_numpy() + np.floor(rng.random(n - 1) * width).astype(int)
    sex = picked.sex.to_numpy()
    lives_alone = rng.random(n - 1) < lives_alone_probability(age, sex)

    m = Maria()
    with_maria = lambda value, rest: np.concatenate([[value], rest])
    df = pd.DataFrame({
        "patient_id": [m.patient_id] + [f"p_{i:05d}" for i in range(2, n + 1)],
        "sex": with_maria(m.sex, sex),
        "age": with_maria(m.age, age),
        "comune_istat": with_maria(m.comune_istat, picked.comune_istat.to_numpy()),
        "lives_alone": with_maria(m.lives_alone, lives_alone),
        "conditions": [list(m.conditions)] + [["HF"]] * (n - 1),
    })
    df["asst_id"] = df.comune_istat.map(comuni.asst_id)

    # MMG: uniform among the MMG of the patient's comune, one vectorised draw for everyone.
    by_comune = mmg.groupby("comune_istat").mmg_id.apply(list)
    counts = df.comune_istat.map(by_comune.str.len()).to_numpy()
    offset = np.floor(rng.random(n) * counts).astype(int)
    df["mmg_id"] = [by_comune[c][o] for c, o in zip(df.comune_istat, offset)]

    hospital = facilities[facilities.type == "hospital"].set_index("asst_id").facility_id
    df["ref_facility_id"] = df.asst_id.map(hospital)
    dist = ref["distances"].set_index(["comune_istat", "facility_id"]).distance_km
    df["distance_km"] = dist.loc[list(zip(df.comune_istat, df.ref_facility_id))].to_numpy()
    return df[PATIENT_COLUMNS], mmg
