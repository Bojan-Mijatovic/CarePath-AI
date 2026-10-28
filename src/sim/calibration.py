"""Outcome calibration against the PNE 30-day HF readmission range (delivery plan step 1.16).

`readmissions` is the one definition of the rate used by the calibration, its test and the notebook:
an ADMISSION within 30 days after a DISCHARGE (SPEC §5.2), counted for discharges on days 0..last−30 so
every index discharge has a full 30-day window.

    uv run python -m sim.calibration   # search the two hazard parameters; copy the result into config
"""

import time

import pandas as pd

from engine import pathway as pathway_model
from sim.population import generate_patients, load_reference
from sim.step import SimParams, Simulator, load_params

TARGET_READMISSION = 0.12  # src/sim/README.md §4
HOSPITAL_RANGE = (0.10, 0.16)
TARGET_DISCHARGES_PER_PATIENT_YEAR = 0.33  # src/sim/README.md §3


def simulate(seed: int = 42, params: SimParams | None = None, days: int = 365, world=None) -> pd.DataFrame:
    """Events of one baseline run, warm-up included."""
    ref, patients = world or (lambda r: (r, generate_patients(seed, r)[0]))(load_reference())
    sim = Simulator(seed, patients, ref, pathway_model.load("hf_lombardia_v1"), params, days)
    return pd.concat(sim.warm_up() + [sim.step(d) for d in range(days)], ignore_index=True)


def readmissions(events: pd.DataFrame, days: int = 365) -> dict:
    dis = events[(events.event_type == "DISCHARGE") & events.day.between(0, days - 31)]
    adm = events[events.event_type == "ADMISSION"][["patient_id", "day"]].rename(columns={"day": "adm"})
    nxt = pd.merge_asof(dis.sort_values("day"), adm.sort_values("adm"), left_on="day", right_on="adm",
                        by="patient_id", direction="forward", allow_exact_matches=False)
    nxt["readmitted"] = (nxt.adm - nxt.day) <= 30
    n_patients = events.patient_id.nunique()
    return {
        "rate": float(nxt.readmitted.mean()),
        "by_hospital": nxt.groupby("facility_id").readmitted.mean().round(4).to_dict(),
        "discharges": int(len(dis)),
        "discharges_per_patient_year": float((events.event_type.eq("DISCHARGE") & events.day.between(0, days - 1)).sum()
                                             / n_patients * 365 / days),
    }


def search(seed: int = 42, iterations: int = 6) -> SimParams:
    """Fixed-point search: the base hazard sets the discharge rate, the post-discharge multiplier sets the
    readmission share. Both respond roughly proportionally, so each update rescales by the ratio."""
    ref = load_reference()
    world = (ref, generate_patients(seed, ref)[0])
    params = load_params()
    for i in range(iterations):
        t = time.perf_counter()
        r = readmissions(simulate(seed, params, world=world))
        print(f"{i}: admission_daily={params.admission_daily:.6f} multiplier={params.post_discharge_multiplier:.2f}"
              f" -> readmission {r['rate']:.4f}, discharges/patient-year {r['discharges_per_patient_year']:.3f}"
              f" ({time.perf_counter() - t:.1f} s)")
        params = params.model_copy(update={
            "admission_daily": round(params.admission_daily
                                     * TARGET_DISCHARGES_PER_PATIENT_YEAR / r["discharges_per_patient_year"], 6),
            "post_discharge_multiplier": round(params.post_discharge_multiplier
                                               * TARGET_READMISSION / r["rate"], 2),
        })
    return params


if __name__ == "__main__":
    search()
