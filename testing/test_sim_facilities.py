import numpy as np
import pandas as pd
import pytest

from sim.reference_data import DATA_DIR

# Demand assumptions from src/sim/README.md §3, until the simulator config of step 1.16 replaces them.
HF_PATIENTS = 10_000
DISCHARGES_PER_PATIENT_YEAR = 0.33  # HF discharges incl. readmissions; one echo and one cardio visit each
BNP_EVERY_DAYS = 90                 # lab_bnp step of hf_lombardia_v1 (SPEC §4)
HEADROOM = 1.25                     # the base table has no bottleneck; scenarios add one (step 1.17)
SERVICES = {"hospital": {"echo", "cardio_visit", "lab"}, "clinic": {"cardio_visit", "lab"}}


@pytest.fixture(scope="module")
def comuni():
    return pd.read_csv(DATA_DIR / "comuni.csv", dtype={"comune_istat": str}).set_index("comune_istat")


@pytest.fixture(scope="module")
def facilities():
    return pd.read_csv(DATA_DIR / "facilities.csv", dtype={"comune_istat": str})


@pytest.fixture(scope="module")
def capacity():
    return pd.read_csv(DATA_DIR / "capacity.csv")


def test_facilities_follow_spec(facilities):
    assert list(facilities.columns) == ["facility_id", "name", "type", "asst_id", "comune_istat", "lat", "lon"]
    assert facilities.facility_id.is_unique
    hospitals = facilities[facilities.type == "hospital"]
    clinics = facilities[facilities.type == "clinic"]
    assert len(hospitals) + len(clinics) == len(facilities)
    assert (hospitals.facility_id.str.fullmatch(r"osp_[A-C]")).all()
    assert (hospitals.name == "Ospedale " + hospitals.facility_id.str[-1]).all()  # invented names (D7)
    assert (clinics.facility_id.str.fullmatch(r"amb_\d+")).all()
    assert (clinics.name == "Poliambulatorio " + clinics.facility_id.str[4:]).all()


def test_one_hospital_per_asst(facilities):
    hospitals = facilities[facilities.type == "hospital"].set_index("facility_id").asst_id.to_dict()
    assert hospitals == {"osp_A": "asst_mantova", "osp_B": "asst_cremona", "osp_C": "asst_crema"}


def test_facilities_sit_in_real_comuni_of_their_asst(facilities, comuni):
    for f in facilities.itertuples():
        c = comuni.loc[f.comune_istat]
        assert c.asst_id == f.asst_id, f.facility_id
        assert (f.lat, f.lon) == (c.lat, c.lon), f.facility_id  # comune centroid, so distances agree


def test_no_facility_in_marias_candidate_comuni(facilities):
    assert not set(facilities.comune_istat) & {"020042", "020038", "020061"}  # src/sim/README.md §3


def test_each_facility_offers_its_services(facilities, capacity):
    offered = capacity.groupby("facility_id").service.apply(set).to_dict()
    for f in facilities.itertuples():
        assert offered[f.facility_id] == SERVICES[f.type], f.facility_id
    assert (capacity.slots_per_day > 0).all()


PER_PATIENT_DAY = {"echo": DISCHARGES_PER_PATIENT_YEAR / 365, "cardio_visit": DISCHARGES_PER_PATIENT_YEAR / 365,
                   "lab": 1 / BNP_EVERY_DAYS}


def test_base_capacity_covers_demand_with_headroom_at_every_facility(comuni, facilities, capacity):
    # Same routing as sim.step: a patient uses the nearest facility of their own ASST offering the service.
    # Checking ASST totals is not enough: in step 1.15 all of Cremona city queued at osp_B for visits.
    dist = pd.read_csv(DATA_DIR / "distances.csv", dtype={"comune_istat": str}).pivot(
        index="comune_istat", columns="facility_id", values="distance_km")[facilities.facility_id]
    patients = HF_PATIENTS * comuni.population_65plus / comuni.population_65plus.sum()
    slots = capacity.set_index(["facility_id", "service"]).slots_per_day
    for service, rate in PER_PATIENT_DAY.items():
        offers = facilities.facility_id.isin(capacity[capacity.service == service].facility_id).to_numpy()
        demand: dict[str, float] = {}
        for code, c in comuni.iterrows():
            usable = offers & (facilities.asst_id.to_numpy() == c.asst_id)
            f = facilities.facility_id.iloc[np.where(usable, dist.loc[code].to_numpy(), np.inf).argmin()]
            demand[f] = demand.get(f, 0) + patients[code] * rate
        for f, d in demand.items():
            assert slots[f, service] >= HEADROOM * d, (f, service, round(d, 2))
