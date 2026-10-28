import pandas as pd
import pytest

from sim.reference_data import DATA_DIR, age_bands, assign_asst, check_province_totals, norm

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


def test_comuni_follow_spec(comuni):
    assert list(comuni.columns) == ["comune_istat", "name", "asst_id", "population", "population_65plus"]
    assert comuni.comune_istat.is_unique
    assert comuni.comune_istat.str.fullmatch(r"0(19|20)\d{3}").all()
    assert (comuni.population_65plus <= comuni.population).all()


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


def test_province_check_catches_a_missing_person():
    comuni = make_comuni()
    pop = pd.DataFrame({"code": ["020001", "019001", "019002"], "age": [70, 70, 70], "males": [5, 3, 2],
                        "females": [1, 1, 1]})
    provinces = pd.DataFrame({"code": ["020", "019"], "age": [70, 70], "males": [5, 5], "females": [1, 2]})
    check_province_totals(pop, comuni, provinces)
    provinces.loc[1, "males"] = 6
    with pytest.raises(ValueError, match="CR"):
        check_province_totals(pop, comuni, provinces)
