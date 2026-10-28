import numpy as np
import pytest
from pydantic import ValidationError

from engine import pathway as pathway_model
from sim.calibration import HOSPITAL_RANGE, readmissions, simulate
from sim.population import generate_patients, load_reference
from sim.step import CONFIG_DIR, SimParams, Simulator, load_params

SEED = 42


@pytest.fixture(scope="module")
def world():
    ref = load_reference()
    return ref, generate_patients(SEED, ref)[0]


@pytest.fixture(scope="module")
def year(world):
    return simulate(SEED, world=world)


def test_readmission_rate_falls_in_the_pne_range(year):
    # Delivery plan step 1.16 "done when"; target and range in src/sim/README.md §4.
    r = readmissions(year)
    assert 0.11 <= r["rate"] <= 0.13
    for hospital, rate in r["by_hospital"].items():
        assert HOSPITAL_RANGE[0] <= rate <= HOSPITAL_RANGE[1], hospital
    assert 0.30 <= r["discharges_per_patient_year"] <= 0.36


def test_weight_rises_before_an_admission(year):
    readings = year[year.event_type == "TELEMON_READING"][["patient_id", "day", "value"]]
    adm = year[year.event_type == "ADMISSION"][["patient_id", "day"]].rename(columns={"day": "adm"})
    m = readings.merge(adm, on="patient_id")
    before = m[(m.adm - m.day).between(1, 3)]
    median = readings.groupby("patient_id").value.median()
    assert (before.value - before.patient_id.map(median)).mean() >= 2  # the pathway rule fires at 2 kg in 3 days


def test_hazard_rises_with_each_risk_factor(world):
    ref, patients = world
    sim = Simulator(SEED, patients, ref, pathway_model.load("hf_lombardia_v1"), days=10)
    r, day = sim.p.risk, 0
    sim.supply_end[:] = day + 30
    sim.telemon_on[:] = False
    base = sim.hazard(day)
    sim.supply_end[0] = day - r.drug_grace_days - 1  # out of drug
    sim.telemon_on[1] = True
    sim.last_discharge[2] = day - 40                 # discharged 40 days ago, nothing done since
    h = sim.hazard(day)
    assert h[0] / base[0] == pytest.approx(np.exp(r.no_drug))
    assert h[1] / base[1] == pytest.approx(np.exp(r.telemonitoring))
    assert h[2] / base[2] == pytest.approx(np.exp(r.overdue_step))
    assert np.allclose(h[3:], base[3:])


def test_config_holds_every_parameter_and_rejects_unknown_ones():
    params = load_params()
    raw = (CONFIG_DIR / "baseline.json").read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="Extra inputs"):
        SimParams.model_validate_json(raw.replace('"warmup_days"', '"warmup_dayz"'))
    assert params.admission_daily > 0
    assert params.post_discharge_multiplier > 1
