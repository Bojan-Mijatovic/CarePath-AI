import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from engine import pathway as pathway_model
from sim.population import generate_patients, load_reference
from sim.step import SCENARIOS_DIR, CapacityChange, CapacityEvent, Scenario, Simulator, load_scenario

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


def test_the_demo_scenarios_have_no_events():
    # D44: the three scenarios of the demo carry only their patterns; events come with what-if (step 2.5).
    assert all(not s.events for s in SCENARIOS)


def test_a_capacity_change_holds_on_its_window_only(world):
    # Step 2.26 (D46): from_day to to_day, both included; open-ended without to_day; a later change wins.
    ref, patients, _, hf = world
    sim = Simulator(42, patients, ref, hf, days=60)
    row = np.flatnonzero((sim.fac_id[sim.res_fac] == "osp_A") & (sim.res_service == "echo"))[0]
    col = lambda day: day - sim.first_day
    base = sim.cap.copy()
    sim.apply_capacity([CapacityChange(facility_id="osp_A", service="echo", slots_per_day=0, from_day=10, to_day=20),
                        CapacityChange(facility_id="osp_A", service="echo", slots_per_day=7, from_day=20)])
    assert (sim.cap[row, col(10):col(20)] == 0).all()
    assert (sim.cap[row, col(20):] == 7).all()
    assert (sim.cap[row, :col(10)] == base[row, :col(10)]).all()
    others = np.arange(len(sim.cap)) != row
    assert (sim.cap[others] == base[others]).all()


def test_events_validate():
    event = {"type": "capacity", "facility_id": "osp_A", "service": "echo", "slots_per_day": 0, "from_day": 10}
    assert CapacityEvent.model_validate(event).to_day is None
    for bad in ({**event, "to_day": 9}, {**event, "slots_per_day": -1}, {k: v for k, v in event.items() if k != "type"},
                {**event, "type": "influenza"}):
        with pytest.raises(ValidationError):
            CapacityEvent.model_validate(bad)


def test_a_renovation_moves_bookings_after_it(world):
    # A renovation is an event of 0 slots for a period: no echo is booked into it at that hospital, and
    # patients book after it instead. Scenario 2's bottleneck is Ospedale B, so Ospedale A's echo is free.
    ref, patients, mmg, hf = world
    closed = CapacityEvent(type="capacity", facility_id="osp_A", service="echo", slots_per_day=0, from_day=5, to_day=25)
    sim = Simulator(42, patients, ref, hf, days=60)
    sim.apply_scenario(SCENARIOS[1].model_copy(update={"events": [closed]}), mmg)
    ev = pd.concat(sim.warm_up() + [sim.step(d) for d in range(60)], ignore_index=True)
    at_a = ev[(ev.event_type == "BOOKING") & (ev.code == "echo") & (ev.facility_id == "osp_A") & (ev.day >= 5)]
    assert not at_a.value.between(5, 25).any()
    assert (at_a.value > 25).sum() > 0
    slots = sim.capacity_slots()
    window = slots[(slots.facility_id == "osp_A") & (slots.service == "echo") & slots.day.between(5, 25)]
    assert (window.slots_total == 0).all()  # tools see it through capacity_slots: the event is no secret


# The demo's situations (D67, proposed): 0 is the normal one, 4 an unplanned closure; 3 stays the investment.

def test_the_situations_hide_no_pattern():
    normal, closure = load_scenario(0), load_scenario(4)
    assert (normal.scenario, closure.scenario) == (0, 4)
    assert not normal.hides_patterns and not normal.events
    assert not closure.hides_patterns
    assert {(e.facility_id, e.service, e.from_day, e.to_day, e.slots_per_day, e.unplanned) for e in closure.events} == {
        ("osp_B", "echo", 30, 59, 0, True), ("osp_B", "cardio_visit", 30, 59, 0, True)}
    assert all(s.hides_patterns for s in SCENARIOS)
    with pytest.raises(ValidationError, match="come together"):
        Scenario(scenario=9, echo_bottleneck=SCENARIOS[0].echo_bottleneck)


def _events(world, scenario: Scenario | None, days: int) -> tuple[Simulator, pd.DataFrame]:
    ref, patients, mmg, hf = world
    sim = Simulator(42, patients, ref, hf, days=days)
    if scenario is not None:
        sim.apply_scenario(scenario, mmg)
    return sim, pd.concat(sim.warm_up() + [sim.step(d) for d in range(days)], ignore_index=True)


def test_the_normal_situation_is_the_world_without_patterns(world):
    _, plain = _events(world, None, 40)
    _, normal = _events(world, load_scenario(0), 40)
    pd.testing.assert_frame_equal(plain, normal)


def test_an_unplanned_closure_is_known_to_nobody_before_its_first_day(world):
    # Day for day the same as the normal situation until day 30; from then the bookings of its window move.
    _, normal = _events(world, load_scenario(0), 70)
    sim, closed = _events(world, load_scenario(4), 70)
    pd.testing.assert_frame_equal(normal[normal.day < 30], closed[closed.day < 30])
    before = normal[(normal.event_type == "BOOKING") & (normal.code == "echo") & (normal.facility_id == "osp_B")
                    & (normal.day < 30) & normal.value.between(30, 59)]
    assert len(before) > 0  # bookings were made into the window before anyone knew

    echo_b = closed[(closed.event_type == "BOOKING") & (closed.code == "echo") & (closed.facility_id == "osp_B")]
    assert not echo_b[echo_b.day >= 30].value.between(30, 59).any()  # nothing is booked into the closure
    again = echo_b[echo_b.day == 30]
    assert len(again) >= len(before) and (again.value >= 60).all()  # asked again on day 30, after it
    for code, event in (("echo", "IMAGING"), ("cardio_visit", "VISIT")):
        at_b = closed[(closed.event_type == event) & (closed.facility_id == "osp_B")]
        assert not at_b.day.between(30, 59).any(), code
    slots = sim.capacity_slots()
    window = slots[(slots.facility_id == "osp_B") & slots.service.isin(["echo", "cardio_visit"]) & slots.day.between(30, 59)]
    assert (window.slots_total == 0).all() and (window.slots_booked == 0).all()


def test_a_partial_unplanned_cut_keeps_the_first_patients(world):
    # 1 slot a day left instead of 3: per day the first booking in patient order stays, the others ask again.
    ref, patients, mmg, hf = world
    cut = CapacityEvent(type="capacity", facility_id="osp_B", service="echo", slots_per_day=1, from_day=30,
                        to_day=59, unplanned=True)
    sim = Simulator(42, patients, ref, hf, days=40)
    sim.apply_scenario(Scenario(scenario=0, events=[cut]), mmg)
    sim.warm_up()
    for d in range(30):
        sim.step(d)
    row = np.flatnonzero((sim.fac_id[sim.res_fac] == "osp_B") & (sim.res_service == "echo"))[0]
    window = slice(30 - sim.first_day, 60 - sim.first_day)
    held = sim.booked[row, window].copy()
    assert held.max() > 1
    sim.step(30)
    after = sim.booked[row, window]
    assert (after <= 1).all()
    assert (after[held >= 1] == 1).all()  # a day that had bookings keeps one; the others may take a request again


def test_an_unplanned_event_must_be_known_to_the_simulator(world):
    ref, patients, mmg, hf = world
    for bad, match in ((dict(facility_id="osp_Z"), "osp_Z"), (dict(from_day=-5), "day 0 or later")):
        event = CapacityEvent(**{"type": "capacity", "facility_id": "osp_B", "service": "echo", "slots_per_day": 0,
                                 "from_day": 30, "unplanned": True, **bad})
        with pytest.raises(ValueError, match=match):
            Simulator(42, patients, ref, hf, days=10).apply_scenario(Scenario(scenario=0, events=[event]), mmg)
