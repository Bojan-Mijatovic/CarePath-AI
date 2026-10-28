import time

import pandas as pd
import pytest

from engine import pathway as pathway_model
from sim.population import generate_patients, load_reference
from sim.step import EVENT_COLUMNS, Simulator

SEED, DAYS = 42, 60
EVENT_TYPES = {"DISCHARGE", "ADMISSION", "VISIT", "IMAGING", "LAB", "DISPENSE", "TELEMON_START",
               "TELEMON_READING", "BOOKING"}  # CALL and REMINDER come from agents (step 1.20)


@pytest.fixture(scope="module")
def world():
    ref = load_reference()
    patients, _ = generate_patients(SEED, ref)
    return ref, patients, pathway_model.load("hf_lombardia_v1")


def simulate(world, days=DAYS, pathway=None, tweak=None):
    ref, patients, hf = world
    sim = Simulator(SEED, patients, ref, pathway or hf, days=days)
    if tweak:
        tweak(sim)
    frames = sim.warm_up() + [sim.step(d) for d in range(days)]
    return sim, pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def run(world):
    return simulate(world)


def test_events_follow_spec(run):
    sim, ev = run
    assert list(ev.columns) == EVENT_COLUMNS  # SPEC §3.1
    assert set(ev.event_type) <= EVENT_TYPES
    assert ev.event_id.is_unique
    assert (ev.source == "sim").all()
    assert ev.action_id.isna().all()
    assert ev.day.min() == sim.first_day  # warm-up kept as history (C11)
    assert ev.day.max() == DAYS - 1
    with_facility = ev.event_type.isin(["ADMISSION", "DISCHARGE", "VISIT", "IMAGING", "LAB", "BOOKING"])
    assert ev.facility_id[with_facility].notna().all()
    assert ev.asst_id[with_facility].notna().all()
    assert ev.facility_id[~with_facility].isna().all()


def test_same_seed_same_events(world, run):
    _, again = simulate(world)
    pd.testing.assert_frame_equal(again, run[1])


def test_capacity_is_never_exceeded_and_slots_respect_the_lead(run):
    sim, ev = run
    assert (sim.booked <= sim.cap).all()
    b = ev[ev.event_type == "BOOKING"]
    assert (b.value >= b.day + sim.p.booking_lead_days).all()


def test_nothing_happens_to_a_patient_in_hospital(run):
    _, ev = run
    stays = ev[ev.event_type.isin(["ADMISSION", "DISCHARGE"])].sort_values(["patient_id", "day", "event_type"])
    other = ev[~ev.event_type.isin(["ADMISSION", "DISCHARGE"])]
    adm = stays[stays.event_type == "ADMISSION"][["patient_id", "day"]].rename(columns={"day": "adm"})
    dis = stays[stays.event_type == "DISCHARGE"][["patient_id", "day"]].rename(columns={"day": "dis"})
    spans = adm.merge(dis, on="patient_id")
    spans = spans[spans.dis > spans.adm].groupby(["patient_id", "adm"], as_index=False).dis.min()
    inside = other.merge(spans, on="patient_id")
    assert not ((inside.day > inside.adm) & (inside.day < inside.dis)).any()


def test_two_arms_share_random_numbers(world, run):
    # Changing one patient's state must not change anybody else's events (common random numbers, AC8).
    _, base = run
    def tweak(sim):
        sim.telemon_on[42] = not sim.telemon_on[42]
    _, other = simulate(world, tweak=tweak)
    pid = world[1].patient_id.iloc[42]
    keep = ["patient_id", "day", "event_type", "code", "value", "facility_id"]
    a = base[base.patient_id != pid][keep].reset_index(drop=True)
    b = other[other.patient_id != pid][keep].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
    assert not base[base.patient_id == pid][keep].reset_index(drop=True).equals(
        other[other.patient_id == pid][keep].reset_index(drop=True))


def test_steps_come_from_the_pathway_not_the_code(world):
    hf = world[2]
    no_telemon = hf.model_copy(update={"steps": [s for s in hf.steps if s.id != "telemon"]})
    sim, ev = simulate(world, days=10, pathway=no_telemon)
    assert not sim.telemon_steps
    unscripted = ev[ev.patient_id != "p_00001"]  # Maria follows her fixed story, not the pathway file
    assert "TELEMON_START" not in set(unscripted.event_type)


def test_one_day_runs_well_under_a_second(world):
    # Early AC2 (delivery plan step 1.15); the full measurement is `uv run carepath-sim`.
    ref, patients, hf = world
    sim = Simulator(SEED, patients, ref, hf, days=30)
    sim.warm_up()
    t = time.perf_counter()
    for d in range(30):
        sim.step(d)
    per_day_ms = (time.perf_counter() - t) / 30 * 1000
    assert per_day_ms < 1000, per_day_ms
