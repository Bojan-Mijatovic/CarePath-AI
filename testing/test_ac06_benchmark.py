"""AC6: Ask correct on at least 8 of 10 benchmark questions.

Measured by: expected answers. Owner: R3. Layer: core. Spec: SPEC.md §11.
The Investigator answers the questions Chiedi shows in the demo (`benchmark.run.DEMO`, from
testing/benchmark/questions.json, step 1.24) on day 35 of the baseline arm, replayed from the cache in
cache_only (D14; `testing/benchmark/run.py --live` fills it), and each conclusion is scored against the value
the tools give (step 2.10); at least 80% must be right. The committed results file of the current prompt
version must say the same, so it cannot go stale.
"""

import json

import pytest

from agents import investigator
from benchmark import run as bench
from benchmark.questions import BENCHMARK, build_runs


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    d = tmp_path_factory.mktemp("benchmark_runs")
    build_runs(d, bench.DEMO)
    try:
        return bench.run(bench.DEMO, live=False, runs_dir=d, only=bench.DEMO)
    finally:
        bench.llm.configure()


@pytest.mark.acceptance
@pytest.mark.parametrize("n", bench.DEMO)
def test_ac06_benchmark(replayed, n):
    got = replayed["scenarios"][str(n)]
    misses = [a["id"] for a in got["answers"] if a["conclusion"].startswith("(nessuna risposta")]
    assert not misses, f"not in the cache: {misses}"
    assert [a["id"] for a in got["answers"]] == list(bench.DEMO[n])
    assert bench.passes(got["correct"], len(got["answers"])), \
        [(a["id"], a["conclusion"]) for a in got["answers"] if not a["correct"]]


def test_the_committed_results_are_the_replay(replayed):
    committed = json.loads((BENCHMARK / f"results_{investigator.ASK_VERSION}.json").read_text(encoding="utf-8"))
    assert committed["prompt_version"] == investigator.ASK_VERSION
    for n in bench.DEMO:
        strip = lambda s: [{k: a[k] for k in ("id", "correct", "conclusion")} for a in s["answers"]]
        assert strip(committed["scenarios"][str(n)]) == strip(replayed["scenarios"][str(n)])


@pytest.mark.parametrize("expected, answer, ok", [
    ({"type": "facility", "value": "Ospedale B"}, "Ospedale B: 41 giorni.", True),
    ({"type": "facility", "value": "Ospedale B"}, "Ospedale A.", False),
    ({"type": "group", "value": "coop_3"}, "La Cooperativa 3 ritira meno.", True),
    ({"type": "group", "value": "coop_3"}, "coop_13", False),
    ({"type": "comuni", "value": ["A", "B", "C", "D", "E"]}, "A, C ed E", True),
    ({"type": "comuni", "value": ["A", "B", "C", "D", "E"]}, "A e B", False),
    ({"type": "number", "value": 0.1213, "tolerance": 0.005}, "Il tasso è del 12,3%.", True),
    ({"type": "number", "value": 0.1213, "tolerance": 0.005}, "Il tasso è del 13,5%.", False),
    ({"type": "number", "value": 17, "tolerance": 0}, "17 pazienti.", True),
    ({"type": "number", "value": 17, "tolerance": 0}, "18 pazienti.", False),
    ({"type": "step", "value": "telemon"}, "Il telemonitoraggio.", True),
    ({"type": "yes_no", "value": False}, "No: 2,1 giorni.", True),
    ({"type": "yes_no", "value": False}, "Sì, ma poco.", False),
    ({"type": "yes_no", "value": True}, "«Sì»: il doppio.", True),
])
def test_the_score(expected, answer, ok):
    assert bench.correct(expected, answer) is ok
