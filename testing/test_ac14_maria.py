"""AC14: Maria's trajectory is identical on every run: readmitted on day 47 without agents, an intervention
on day 31 with them (delivery plan step 1.19: 10 runs out of 10)."""

import pandas as pd
import pytest

from engine import pathway as pathway_model
from sim import maria
from sim.population import generate_patients, load_reference
from sim.step import Simulator, load_scenario

DAYS = 60
RUNS = [(seed, scenario) for seed, scenario in zip((1, 2, 3, 4, 5), (1, 2, 3, 1, 2))]  # x 2 arms = 10 runs
KEEP = ["day", "event_type", "code", "value", "facility_id", "source", "action_id"]


@pytest.fixture(scope="module")
def ref():
    return load_reference()


def maria_events(ref, seed, scenario, call):
    patients, mmg = generate_patients(seed, ref)
    sim = Simulator(seed, patients, ref, pathway_model.load("hf_lombardia_v1"), days=DAYS)
    sim.apply_scenario(load_scenario(scenario), mmg)
    frames = sim.warm_up()
    for d in range(DAYS):
        if call and d == 31:
            assert sim.receive_call(maria.PATIENT_ID, d, "act_s_agents_1")
        frames.append(sim.step(d))
    ev = pd.concat(frames, ignore_index=True)
    return ev[ev.patient_id == maria.PATIENT_ID][KEEP].reset_index(drop=True)


@pytest.fixture(scope="module")
def runs(ref):
    return {(seed, sc, call): maria_events(ref, seed, sc, call) for seed, sc in RUNS for call in (False, True)}


def days_of(ev, event_type):
    return ev[ev.event_type == event_type].day.tolist()


@pytest.mark.acceptance
@pytest.mark.parametrize("call", [False, True], ids=["without_agents", "with_agents"])
def test_ac14_identical_on_every_run(runs, call):
    arm = [ev for (seed, sc, c), ev in runs.items() if c == call]
    assert len(arm) == 5
    for ev in arm[1:]:
        pd.testing.assert_frame_equal(ev, arm[0])


@pytest.mark.acceptance
def test_ac14_without_agents_readmitted_on_day_47(runs):
    ev = runs[RUNS[0] + (False,)]
    assert days_of(ev, "DISCHARGE") == [0, 55]
    assert days_of(ev, "ADMISSION") == [-8, 47]
    # Nothing between her supply running out on day 0 and the readmission; she collects again after it.
    assert days_of(ev, "DISPENSE") == [-120, -90, -60, -30, 56]
    assert days_of(ev, "TELEMON_START") == [6]
    assert days_of(ev, "VISIT") == [24]
    assert days_of(ev, "CALL") == []
    assert days_of(ev, "LAB") == []
    w = ev[ev.event_type == "TELEMON_READING"].set_index("day").value
    assert w[46] - w[39] > 4  # weight rises from day 40, which the 2 kg / 3 days rule sees
    assert (ev.source == "sim").all()


@pytest.mark.acceptance
def test_ac14_with_agents_call_on_31_delivery_33_hba1c_40_no_readmission(runs):
    ev = runs[RUNS[0] + (True,)]
    assert days_of(ev, "CALL") == [31]
    assert 33 in days_of(ev, "DISPENSE")
    lab = ev[ev.event_type == "LAB"]
    assert lab.day.tolist() == [40]
    assert lab.code.tolist() == [maria.HBA1C]
    assert days_of(ev, "ADMISSION") == [-8]  # no readmission
    effects = ev[(ev.day >= 31) & ev.event_type.isin(["CALL", "DISPENSE", "LAB", "BOOKING"])]
    assert (effects.source == "agent_action").all()
    assert (effects.action_id == "act_s_agents_1").all()
    w = ev[ev.event_type == "TELEMON_READING"].set_index("day").value
    assert abs(w[46] - w[39]) < 2  # no decompensation


def test_arms_differ_only_after_the_call(runs):
    without, with_ = runs[RUNS[0] + (False,)], runs[RUNS[0] + (True,)]
    pd.testing.assert_frame_equal(without[without.day < 31].reset_index(drop=True),
                                  with_[with_.day < 31].reset_index(drop=True))


def test_a_call_outside_the_window_changes_nothing():
    script = maria.MariaScript(-120, 60)
    assert not script.receive_call(20, "act_x")
    assert not script.receive_call(50, "act_x")
    assert script.receive_call(31, "act_x")
    assert not script.receive_call(32, "act_y")  # only the first call counts
