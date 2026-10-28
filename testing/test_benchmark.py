"""Benchmark questions (delivery plan step 1.24): up to date, answerable with the tools, right about the
patterns, and with at least 3 questions whose answer is "no"."""

import json

import pytest

from benchmark.questions import BENCHMARK, SCENARIOS, build_runs, text
from sim.truth import TRUTH_DIR

TYPES = {"facility", "group", "comuni", "number", "step", "yes_no"}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("benchmark")
    build_runs(d)
    return d


@pytest.fixture(scope="module")
def committed():
    return json.loads((BENCHMARK / "questions.json").read_text(encoding="utf-8"))


def test_committed_questions_match_the_tools(runs):
    # Regenerate with: uv run python testing/benchmark/questions.py
    assert (BENCHMARK / "questions.json").read_text(encoding="utf-8") == text(runs)


def test_ten_questions_per_scenario_in_two_languages(committed):
    assert set(committed["scenarios"]) == {str(n) for n in SCENARIOS}
    ids = None
    for qs in committed["scenarios"].values():
        assert len(qs) == 10
        ids = ids or [q["id"] for q in qs]
        assert [q["id"] for q in qs] == ids
        for q in qs:
            for text_ in (q["question"], q["answer"]):
                assert set(text_) == {"it", "en"}
                assert all(text_.values())
            assert q["expected"]["type"] in TYPES
            assert q["calls"], "every answer comes from a tool call"
        noes = [q for q in qs if q["expected"]["type"] == "yes_no" and q["expected"]["value"] is False]
        assert len(noes) >= 3


@pytest.mark.parametrize("n", SCENARIOS)
def test_pattern_answers_match_the_hidden_places(committed, n):
    truth = json.loads((TRUTH_DIR / f"scenario_{n}.json").read_text(encoding="utf-8"))
    qs = {q["id"]: q["expected"]["value"] for q in committed["scenarios"][str(n)]}
    hospital = {"osp_A": "Ospedale A", "osp_B": "Ospedale B", "osp_C": "Ospedale C"}
    assert qs["q01_echo_wait"] == hospital[truth["echo_bottleneck"]["facility_id"]]
    assert qs["q03_low_dispensing_group"] == truth["low_adherence_group"]["coop_id"]
    assert set(qs["q04_telemonitoring_comuni"]) & set(truth["rural_dropout_comuni"])
    assert 0.10 <= qs["q05_readmission_rate"] <= 0.16  # PNE range (step 1.16)
