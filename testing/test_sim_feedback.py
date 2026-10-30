import numpy as np
import pandas as pd
import pytest

from engine import pathway as pathway_model
from sim import feedback
from sim.population import generate_patients, load_reference
from sim.step import EVENT_COLUMNS, NO_DAY, Simulator, load_scenario

DAYS, D = 20, 10


@pytest.fixture(scope="module")
def world():
    ref = load_reference()
    return ref, generate_patients(42, ref)[0], pathway_model.load("hf_lombardia_v1")


def run(world, actions=None):
    ref, patients, hf = world
    sim = Simulator(42, patients, ref, hf, days=DAYS)
    feedback.register("s1_agents", sim)
    frames, recorded = sim.warm_up(), None
    try:
        for d in range(DAYS):
            frames.append(sim.step(d))
            if actions and d == D:
                recorded = feedback.apply("s1_agents", actions)
    finally:
        feedback.unregister("s1_agents")
    return pd.concat(frames, ignore_index=True), recorded


def action(type_, patient="p_00042", n=1):
    return {"action_id": f"act_s1_agents_{n}", "type": type_, "patient_id": patient, "executed_day": D,
            "payload": {}}


def test_calls_and_reminders_are_recorded_on_the_day_they_run(world):
    _, rec = run(world, [action("call_task"), action("reminder", "p_00043", 2), action("notify_mmg", n=3)])
    assert list(rec.columns) == EVENT_COLUMNS  # SPEC §3.1
    assert rec.event_type.tolist() == ["CALL", "REMINDER"]  # notify_mmg leaves no patient event
    assert (rec.day == D).all()
    assert (rec.source == "agent_action").all()
    assert rec.action_id.tolist() == ["act_s1_agents_1", "act_s1_agents_2"]


def test_an_action_without_an_effect_changes_nothing(world):
    base, _ = run(world)
    called, _ = run(world, [action(t, n=i) for i, t in enumerate(["call_task", "notify_mmg"])])
    keep = ["patient_id", "day", "event_type", "code", "value", "facility_id"]
    sim_only = lambda ev: ev[ev.source == "sim"][keep].reset_index(drop=True)
    pd.testing.assert_frame_equal(sim_only(base), sim_only(called))


def sim_at(world, day: int, scenario: int | None = None) -> Simulator:
    ref, patients, hf = world
    sim = Simulator(42, patients, ref, hf, days=day + 20)
    if scenario:
        sim.apply_scenario(load_scenario(scenario), generate_patients(42, ref)[1])
    sim.warm_up()
    for d in range(day + 1):
        sim.step(d)
    return sim


def scoped(type_: str, targets: list[dict], payload: dict | None = None) -> pd.DataFrame:
    return pd.DataFrame([{"action_id": "act_s1_agents_1", "type": type_, "patient_id": None, "executed_day": D,
                          "payload": {"patients": targets} | (payload or {})}])


def test_a_call_during_a_decompensation_averts_some_admissions(world):
    # Step 2.13: the decompensation window of step 1.16 is where a call can act (effect `review`).
    base, called = sim_at(world, D), sim_at(world, D)
    ongoing = np.flatnonzero((base.decomp_start > NO_DAY) & (base.decomp_admit > D))
    assert len(ongoing) > 10
    called.apply_actions(D, scoped("call_task", [{"patient_id": base.patient_id[i], "effect": "review"} for i in ongoing]))
    caught = (called.decomp_admit[ongoing] == NO_DAY).mean()
    assert 0.3 < caught < 0.9  # call_task review 0.6 in the config
    assert (base.decomp_admit[ongoing] > D).all()  # without the call every one of them is still coming in


def test_a_reminder_books_an_overdue_step(world):
    sim = sim_at(world, D)
    free = np.flatnonzero((sim.book_on["echo"] == NO_DAY) & (sim.appt_day["echo"] <= D) & ~sim.in_hosp)[:400]
    rec = sim.apply_actions(D, scoped("reminder", [{"patient_id": sim.patient_id[i], "effect": "book", "step": "echo"}
                                                   for i in free]))
    assert (rec.event_type == "REMINDER").sum() == len(free)
    asked = (sim.book_on["echo"][free] == D + 1).mean()
    assert 0.2 < asked < 0.4  # reminder book 0.3


def test_a_reschedule_moves_bookings_to_an_earlier_slot_elsewhere(world):
    day = 30  # scenario 1: echo bottleneck at osp_A from day 0, spare slots at osp_B
    sim = sim_at(world, day, scenario=1)
    r_a = next(r for r in np.flatnonzero(sim.res_service == "echo") if sim.fac_id[sim.res_fac[r]] == "osp_A")
    waiting = np.flatnonzero((sim.appt_res["echo"] == r_a) & (sim.appt_day["echo"] > day + 20))
    assert len(waiting) > 10
    booked_before, old = sim.booked.sum(), sim.appt_day["echo"][waiting].copy()
    action = scoped("reschedule", [], {"service": "echo", "from_facility": "osp_A", "to_facility": "osp_B",
                                       "patients": list(sim.patient_id[waiting])}).assign(executed_day=day)
    rec = sim.apply_actions(day, action)
    moved = sim.appt_res["echo"][waiting] != r_a
    assert moved.sum() > 10
    assert (sim.appt_day["echo"][waiting][moved] < old[moved]).all()
    assert (rec.event_type == "BOOKING").sum() == moved.sum()
    assert set(rec.facility_id) == {"osp_B"}
    assert sim.booked.sum() == booked_before  # every slot taken at osp_C was given back at osp_A


@pytest.mark.parametrize("bad, message", [
    ([{**action("call_task"), "type": "teleport"}], "unknown action types"),
    ([{k: v for k, v in action("call_task").items() if k != "executed_day"}], "need the columns"),
    ([action("call_task"), {**action("reminder"), "executed_day": D + 1}], "one day at a time"),
    ([action("call_task", "p_99999")], "unknown patient"),
])
def test_bad_actions_are_rejected(world, bad, message):
    ref, patients, hf = world
    feedback.register("s1_agents", Simulator(42, patients, ref, hf, days=DAYS))
    try:
        with pytest.raises(ValueError, match=message):
            feedback.apply("s1_agents", bad)
    finally:
        feedback.unregister("s1_agents")


def test_unknown_run_and_empty_day():
    with pytest.raises(KeyError):
        feedback.apply("s3_agents", [action("call_task")])
    feedback.register("s3_agents", None)
    try:
        assert list(feedback.apply("s3_agents", pd.DataFrame(columns=feedback.REQUIRED)).columns) == EVENT_COLUMNS
    finally:
        feedback.unregister("s3_agents")
