import json

import pandas as pd
import pytest

from sim.reference_data import (DATA_DIR, GEOJSON_PATH, age_bands, assign_asst, centroid, check_province_totals,
                                geometry, norm, signed_area)

# ATS Val Padana lies inside this box (lat, lon); anything outside means a projection or axis-order bug.
LAT, LON = (44.9, 45.6), (9.4, 11.5)

# Totals from ISTAT POSAS at 1 Jan 2025, as documented in src/sim/README.md §2.
ASST_TOTALS = {
    "asst_mantova": (64, 407_744, 100_761),
    "asst_cremona": (65, 192_424, 50_578),
    "asst_crema": (48, 161_499, 39_879),
}


@pytest.fixture(scope="module")
def comuni():
    return pd.read_csv(DATA_DIR / "comuni.csv", dtype={"comune_istat": str})


@pytest.fixture(scope="module")
def population():
    return pd.read_csv(DATA_DIR / "population_by_age.csv", dtype={"comune_istat": str})


def test_totals_match_istat_for_each_asst(comuni):
    got = comuni.groupby("asst_id").agg(n=("comune_istat", "size"), pop=("population", "sum"),
                                        old=("population_65plus", "sum"))
    assert {a: tuple(int(v) for v in row) for a, row in got.iterrows()} == ASST_TOTALS


@pytest.fixture(scope="module")
def geojson():
    return json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))


def test_comuni_follow_spec(comuni):
    assert list(comuni.columns) == ["comune_istat", "name", "asst_id", "population", "population_65plus", "lat", "lon"]
    assert comuni.comune_istat.is_unique
    assert comuni.comune_istat.str.fullmatch(r"0(19|20)\d{3}").all()
    assert (comuni.population_65plus <= comuni.population).all()
    assert comuni.lat.between(*LAT).all() and comuni.lon.between(*LON).all()


def test_geojson_has_every_comune_and_fits_the_budget(comuni, geojson):
    codes = [f["properties"]["comune_istat"] for f in geojson["features"]]
    assert codes == comuni.comune_istat.tolist()
    assert GEOJSON_PATH.stat().st_size < 2_000_000  # delivery plan, step 1.11


def test_geojson_follows_rfc7946_and_stays_in_the_ats(geojson):
    for f in geojson["features"]:
        assert f["geometry"]["type"] == "MultiPolygon"
        for outer, *holes in f["geometry"]["coordinates"]:
            assert signed_area(outer) > 0, f["properties"]["name"]  # counter-clockwise
            assert all(signed_area(h) < 0 for h in holes)
            assert all(LON[0] <= lon <= LON[1] and LAT[0] <= lat <= LAT[1] for lon, lat in outer)


def test_centroid_lies_inside_its_comune_box(comuni, geojson):
    for f, row in zip(geojson["features"], comuni.itertuples()):
        pts = [p for poly in f["geometry"]["coordinates"] for p in poly[0]]
        assert min(p[0] for p in pts) <= row.lon <= max(p[0] for p in pts), row.name
        assert min(p[1] for p in pts) <= row.lat <= max(p[1] for p in pts), row.name


def test_age_bands_add_up_to_each_comune(comuni, population):
    summed = population.groupby("comune_istat").population.sum()
    assert summed.equals(comuni.set_index("comune_istat").population.rename("population"))
    assert set(population.sex) == {"F", "M"}
    assert population.loc[population.age_from == 100, "age_to"].isna().all()


@pytest.mark.parametrize("name, asst", [("Mantova", "asst_mantova"), ("Cremona", "asst_cremona"),
                                        ("Crema", "asst_crema"), ("Poggio Rusco", "asst_mantova"),
                                        ("Casalmaggiore", "asst_cremona")])
def test_demo_comuni_are_in_the_right_asst(comuni, name, asst):
    assert comuni.loc[comuni.name == name, "asst_id"].tolist() == [asst]


def test_norm_ignores_case_accents_and_punctuation():
    assert norm("Casalbuttano Ed Uniti") == norm("Casalbuttano ed Uniti")
    assert norm("Pieve D'Olmi") == norm("Pieve d'Olmi")
    assert norm("Cingia De' Botti") == norm("Cingia de' Botti")


def make_comuni():
    return pd.DataFrame({"comune_istat": ["020001", "019001", "019002"],
                         "name": ["Asola", "Cremona", "Agnadello"], "province": ["MN", "CR", "CR"]})


def test_assign_asst_splits_cremona_by_the_ats_list():
    assert assign_asst(make_comuni(), ["CREMONA"]).tolist() == ["asst_mantova", "asst_cremona", "asst_crema"]


def test_assign_asst_fails_on_a_name_istat_does_not_know():
    with pytest.raises(ValueError, match="cremonaovest"):
        assign_asst(make_comuni(), ["Cremona Ovest"])


def test_age_bands_cap_at_100_and_split_by_sex():
    pop = pd.DataFrame({"code": ["019001"] * 4, "age": [0, 4, 5, 100], "males": [1, 2, 3, 4],
                        "females": [10, 20, 30, 40]})
    out = age_bands(pop)
    m = out[out.sex == "M"].set_index("age_from").population.to_dict()
    assert m == {0: 3, 5: 3, 100: 4}
    assert out.population.sum() == 110


def square(x0, y0, size, clockwise):
    ring = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size), (x0, y0)]
    return ring[::-1] if clockwise else ring


@pytest.mark.parametrize("ox, oy", [(0, 0), (640_000, 5_000_000)])
def test_centroid_subtracts_holes_and_keeps_precision_at_utm_scale(ox, oy):
    # 10 × 10 square with a 2 × 2 hole at (6..8, 6..8): x = (100·5 − 4·7) / 96
    rings = [square(ox, oy, 10, clockwise=True), square(ox + 6, oy + 6, 2, clockwise=False)]
    cx, cy = centroid(rings)
    assert cx - ox == pytest.approx(472 / 96) and cy - oy == pytest.approx(472 / 96)


def test_geometry_reverses_winding_and_nests_holes():
    rings = [square(640_000, 5_000_000, 1000, clockwise=True), square(640_400, 5_000_400, 100, clockwise=False),
             square(650_000, 5_000_000, 1000, clockwise=True)]
    polygons = geometry(rings)["coordinates"]
    assert [len(p) for p in polygons] == [2, 1]
    assert signed_area(polygons[0][0]) > 0 and signed_area(polygons[0][1]) < 0


def test_province_check_catches_a_missing_person():
    comuni = make_comuni()
    pop = pd.DataFrame({"code": ["020001", "019001", "019002"], "age": [70, 70, 70], "males": [5, 3, 2],
                        "females": [1, 1, 1]})
    provinces = pd.DataFrame({"code": ["020", "019"], "age": [70, 70], "males": [5, 5], "females": [1, 2]})
    check_province_totals(pop, comuni, provinces)
    provinces.loc[1, "males"] = 6
    with pytest.raises(ValueError, match="CR"):
        check_province_totals(pop, comuni, provinces)
