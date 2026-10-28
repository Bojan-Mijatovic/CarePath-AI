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


def daily_demand(share: float) -> dict[str, float]:
    discharges = HF_PATIENTS * share * DISCHARGES_PER_PATIENT_YEAR / 365
    return {"echo": discharges, "cardio_visit": discharges, "lab": HF_PATIENTS * share / BNP_EVERY_DAYS}


def test_base_capacity_covers_demand_with_headroom_in_every_asst(comuni, facilities, capacity):
    share = comuni.groupby("asst_id").population_65plus.sum() / comuni.population_65plus.sum()
    slots = capacity.merge(facilities[["facility_id", "asst_id"]]).groupby(["asst_id", "service"]).slots_per_day.sum()
    for asst, s in share.items():
        for service, demand in daily_demand(s).items():
            assert slots[asst, service] >= HEADROOM * demand, (asst, service)
