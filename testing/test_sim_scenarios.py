import pandas as pd
import pytest
from pydantic import ValidationError

from engine import pathway as pathway_model
from sim.population import generate_patients, load_reference
from sim.step import SCENARIOS_DIR, Scenario, Simulator, load_scenario

SCENARIOS = [load_scenario(n) for n in (1, 2, 3)]


@pytest.fixture(scope="module")
def world():
    ref = load_reference()
    patients, mmg = generate_patients(42, ref)
    return ref, patients, mmg, pathway_model.load("hf_lombardia_v1")


def test_files_validate_and_match_their_number():
    for n, sc in zip((1, 2, 3), SCENARIOS):
        assert sc.scenario == n
    with pytest.raises(ValidationError):
        Scenario.model_validate_json((SCENARIOS_DIR / "1.json").read_text().replace('"coop_id"', '"coop"'))


def test_same_pattern_types_in_different_places(world):
    # Delivery plan step 1.17 "done when".
    ref, _, mmg, _ = world
    bottleneck = [s.echo_bottleneck.facility_id for s in SCENARIOS]
    assert len(set(bottleneck)) == 3
    assert all(s.echo_free_capacity.facility_id != s.echo_bottleneck.facility_id for s in SCENARIOS)
    coop_asst = mmg.drop_duplicates("coop_id").set_index("coop_id").comune_istat.map(
        ref["comuni"].set_index("comune_istat").asst_id)
    assert len({coop_asst[s.low_adherence.coop_id] for s in SCENARIOS}) == 3  # one per ASST
    comuni = [set(s.rural_dropout.comuni) for s in SCENARIOS]
    assert not comuni[0] & comuni[1]
    assert not comuni[0] & comuni[2]
    assert not comuni[1] & comuni[2]


def test_rural_comuni_are_far_from_their_own_hospital(world):
    ref = world[0]
    asst = ref["comuni"].set_index("comune_istat").asst_id
    hospital = ref["facilities"][ref["facilities"].type == "hospital"].set_index("asst_id").facility_id
    dist = ref["distances"].set_index(["comune_istat", "facility_id"]).distance_km
    for s in SCENARIOS:
        for c in s.rural_dropout.comuni:
            assert dist[c, hospital[asst[c]]] > s.rural_dropout.min_distance_km, (s.scenario, c)


@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: f"scenario_{s.scenario}")
def test_patterns_show_in_the_data(world, sc):
    ref, patients, mmg, hf = world
    sim = Simulator(42, patients, ref, hf, days=60)
    sim.apply_scenario(sc, mmg)
    ev = pd.concat(sim.warm_up() + [sim.step(d) for d in range(60)], ignore_index=True)

    # Pattern 1: about six weeks of echo wait at the bottleneck around day 35, normal waits elsewhere.
    b = ev[(ev.event_type == "BOOKING") & (ev.code == "echo") & ev.day.between(30, 40)]
    wait = (b.value - b.day).groupby(b.facility_id).mean()
    assert 30 <= wait[sc.echo_bottleneck.facility_id] <= 55
    assert (wait.drop(sc.echo_bottleneck.facility_id) < 7).all()
    free = sim.cap[:, 60 - sim.first_day] - sim.booked[:, 60 - sim.first_day]
    by_fac = pd.Series(free, index=sim.fac_id[sim.res_fac])[sim.res_service == "echo"]
    assert by_fac[sc.echo_free_capacity.facility_id] > 0

    # Pattern 2: the cooperative collects its drug far less often.
    in_coop = patients.mmg_id.map(mmg.set_index("mmg_id").coop_id).eq(sc.low_adherence.coop_id).to_numpy()
    disp = patients.patient_id.map(ev[ev.event_type == "DISPENSE"].groupby("patient_id").size()).fillna(0).to_numpy()
    assert disp[in_coop].mean() < 0.8 * disp[~in_coop].mean()

    # Pattern 3: hit patients have almost left telemonitoring.
    hit = sim.telemon_dropout_p > sim.p.telemon_dropout_daily
    assert hit.sum() >= 30
    assert sim.telemon_on[hit].mean() < 0.5 * sim.telemon_on[~hit].mean()


def test_unknown_places_are_rejected(world):
    ref, patients, mmg, hf = world
    bad = SCENARIOS[0].model_copy(update={"low_adherence": SCENARIOS[0].low_adherence.model_copy(update={"coop_id": "coop_99"})})
    with pytest.raises(ValueError, match="coop_99"):
        Simulator(42, patients, ref, hf, days=10).apply_scenario(bad, mmg)
    bad = SCENARIOS[0].model_copy(update={"echo_bottleneck": SCENARIOS[0].echo_bottleneck.model_copy(update={"facility_id": "osp_Z"})})
    with pytest.raises(ValueError, match="osp_Z"):
        Simulator(42, patients, ref, hf, days=10).apply_scenario(bad, mmg)
