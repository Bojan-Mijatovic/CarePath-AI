import pandas as pd
import pytest

from sim.population import N_HF_PATIENTS, PATIENT_COLUMNS, Maria, generate_patients, load_reference
from sim.rng import component_rng

SEED = 42


@pytest.fixture(scope="module")
def ref():
    return load_reference()


@pytest.fixture(scope="module")
def population(ref):
    return generate_patients(SEED, ref)


def test_patients_follow_spec(population):
    patients, _ = population
    assert list(patients.columns) == PATIENT_COLUMNS  # SPEC §3.2 `patients`
    assert len(patients) == N_HF_PATIENTS
    assert patients.patient_id.tolist() == [f"p_{i:05d}" for i in range(1, N_HF_PATIENTS + 1)]
    assert set(patients.sex) == {"F", "M"}
    assert patients.age.between(45, 104).all()
    assert patients.conditions.map(lambda c: "HF" in c).all()


def test_maria_is_p00001_in_every_seed(ref):
    m = Maria()
    for seed in (SEED, 7):
        row = generate_patients(seed, ref)[0].iloc[0]
        assert (row.patient_id, row.sex, row.age, row.comune_istat, row.lives_alone) == \
               (m.patient_id, m.sex, m.age, m.comune_istat, m.lives_alone)
        assert row.conditions == ["HF", "T2D"] and row.ref_facility_id == "osp_A" and row.distance_km == 44.8


def test_only_maria_has_diabetes_until_option_b(population):
    patients, _ = population
    assert patients.conditions.map(lambda c: "T2D" in c).sum() == 1


def test_patients_are_consistent_with_reference_data(population, ref):
    patients, mmg = population
    comuni = ref["comuni"].set_index("comune_istat")
    assert (patients.asst_id == patients.comune_istat.map(comuni.asst_id)).all()
    assert (patients.comune_istat == patients.mmg_id.map(mmg.set_index("mmg_id").comune_istat)).all()
    hospital = {"asst_mantova": "osp_A", "asst_cremona": "osp_B", "asst_crema": "osp_C"}
    assert (patients.ref_facility_id == patients.asst_id.map(hospital)).all()
    dist = ref["distances"].set_index(["comune_istat", "facility_id"]).distance_km
    assert patients.distance_km.tolist() == dist.loc[list(zip(patients.comune_istat, patients.ref_facility_id))].tolist()


def test_patients_spread_like_the_population_aged_65_plus(population, ref):
    patients, _ = population
    comuni = ref["comuni"]
    expected = comuni.groupby("asst_id").population_65plus.sum() / comuni.population_65plus.sum()
    got = patients.asst_id.value_counts(normalize=True)
    assert (got - expected).abs().max() < 0.02


def test_hf_population_is_old_and_women_live_alone_more(population):
    patients, _ = population
    assert 74 <= patients.age.mean() <= 81  # mean age of HF patients in the assumption, README §7
    old = patients[patients.age >= 75]
    assert old[old.sex == "F"].lives_alone.mean() > old[old.sex == "M"].lives_alone.mean() + 0.1


def test_mmg_and_cooperatives_follow_spec(population, ref):
    _, mmg = population
    assert list(mmg.columns) == ["mmg_id", "coop_id", "cs_id", "comune_istat"]  # SPEC §3.2 `mmg`
    assert mmg.mmg_id.is_unique and mmg.mmg_id.str.fullmatch(r"mmg_\d{3}").all()
    assert set(mmg.comune_istat) == set(ref["comuni"].comune_istat)  # every comune has an MMG
    assert (mmg.cs_id == mmg.coop_id.str.replace("coop_", "cs_")).all()
    asst = mmg.comune_istat.map(ref["comuni"].set_index("comune_istat").asst_id)
    assert (asst.groupby(mmg.coop_id).nunique() == 1).all()  # a cooperative never crosses an ASST
    assert mmg.groupby("comune_istat").coop_id.nunique().max() == 1  # nor splits a comune
    assert mmg.groupby("coop_id").size().between(15, 60).all()


def test_same_seed_same_population_other_seed_differs(ref, population):
    again, _ = generate_patients(SEED, ref)
    pd.testing.assert_frame_equal(again, population[0])
    other, _ = generate_patients(SEED + 1, ref)
    assert not other.iloc[1:].reset_index(drop=True).equals(population[0].iloc[1:].reset_index(drop=True))


def test_component_streams_are_stable_and_independent():
    assert component_rng(1, "population").random() == component_rng(1, "population").random()
    assert component_rng(1, "population").random() != component_rng(1, "dispensing").random()
    assert component_rng(1, "population").random() != component_rng(2, "population").random()
