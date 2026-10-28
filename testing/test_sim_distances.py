import pandas as pd
import pytest

from sim.reference_data import DATA_DIR, ROAD_FACTOR, haversine_km

MARIA_COMUNE = "020042"  # Poggio Rusco, src/sim/README.md §3


@pytest.fixture(scope="module")
def dist():
    return pd.read_csv(DATA_DIR / "distances.csv", dtype={"comune_istat": str}).set_index(["comune_istat", "facility_id"])


def test_matrix_covers_every_comune_and_facility(dist):
    comuni = pd.read_csv(DATA_DIR / "comuni.csv", dtype={"comune_istat": str})
    facilities = pd.read_csv(DATA_DIR / "facilities.csv")
    assert len(dist) == len(comuni) * len(facilities)
    assert set(dist.index.get_level_values(0)) == set(comuni.comune_istat)
    assert set(dist.index.get_level_values(1)) == set(facilities.facility_id)
    assert dist.distance_km.between(0, 250).all()


def test_maria_lives_about_45_km_from_her_hospital(dist):
    # Delivery plan step 1.13 "done when"; Solution Plan §6: rural comune 45 km from the hospital.
    assert dist.loc[(MARIA_COMUNE, "osp_A"), "distance_km"] == pytest.approx(45, abs=1)


def test_maria_has_no_service_close_to_home(dist):
    assert dist.loc[MARIA_COMUNE].distance_km.min() > 40  # pattern 3: far from every facility


def test_a_facility_is_zero_km_from_its_own_comune(dist):
    assert dist.loc[("020030", "osp_A"), "distance_km"] == 0  # Mantova


def test_haversine_matches_one_degree_of_latitude():
    assert haversine_km(45.0, 10.0, 46.0, 10.0) == pytest.approx(111.195, abs=0.01)


def test_road_factor_is_applied(dist):
    straight = haversine_km(45.14921, 10.80695, 45.14092, 10.02977)  # osp_A to osp_B comune centroids
    assert dist.loc[("019036", "osp_A"), "distance_km"] == round(ROAD_FACTOR * straight, 1)
