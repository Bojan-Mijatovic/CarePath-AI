import pandas as pd
import pytest

from engine import pathway as pathway_model
from sim import feedback
from sim.population import generate_patients, load_reference
from sim.step import EVENT_COLUMNS, Simulator

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


def test_effects_are_a_no_op_until_step_2_13(world):
    base, _ = run(world)
    called, _ = run(world, [action(t, n=i) for i, t in enumerate(["call_task", "reschedule", "notify_mmg"])])
    keep = ["patient_id", "day", "event_type", "code", "value", "facility_id"]
    pd.testing.assert_frame_equal(base[keep].reset_index(drop=True), called[keep].reset_index(drop=True))


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
