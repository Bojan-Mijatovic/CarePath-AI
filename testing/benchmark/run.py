"""Benchmark run (delivery plan step 2.10, AC6): the Investigator answers benchmark questions (questions.json,
step 1.24) on day 35 of the baseline arm, with the tools only, and each answer is scored against the expected
value the tools give.

    uv run python testing/benchmark/run.py [--live]                              # the demo's questions (DEMO)
    uv run python testing/benchmark/run.py [1 2 3] [q01_echo_wait ...] [--live]  # a trial, not a result

--live calls qwen3:30b-instruct for every answer the cache lacks and stores it in demo/cache/ (about 5–7
minutes a question on the team laptops); without it the answers are replayed from the cache, and a miss is a
wrong answer. Only the demo's questions are a result, in testing/benchmark/results_<prompt version>.json.

The score reads only the conclusion, the sentence a user reads as the answer: a hospital, an MMG group or a
step by its name, three of the five comuni, a number within the question's tolerance, or "Sì"/"No" first.
"""

import json
import math
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # testing/, as pytest has it

from agents import investigator, llm, tools
from benchmark.questions import BENCHMARK, DAY, SCENARIOS, build_runs
from engine import pathway as pathway_model

PATHWAY = pathway_model.load("hf_lombardia_v1")
PASS_SHARE = 0.8  # AC6: at least 8 of 10, as a share of the questions asked
# The questions Chiedi shows in the demo, the only ones warmed and scored (the lead, 30 Oct 2026: a demo app,
# no 3-hour warm-up of all 30). q01 goes with the prototype's echo question; q08–q10 show that the agent says
# no. q03 (the prototype's "Koji MMG…") was tried first and named one MMG, MMG_082, instead of a group.
DEMO = {2: ("q01_echo_wait", "q08_no_echo_problem", "q09_no_dispensing_problem", "q10_no_telemonitoring_problem")}
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def numbers(text: str) -> list[float]:
    """Numbers in an Italian or English sentence; a percentage counts as a fraction too."""
    out = []
    for m in NUMBER.finditer(text):
        x = float(m.group().replace(",", "."))
        out.append(x)
        if text[m.end():m.end() + 1] == "%":
            out.append(round(x / 100, 6))
    return out


def correct(expected: dict, answer: str) -> bool:
    kind, value, text = expected["type"], expected["value"], answer.strip()
    if kind == "facility":
        return value in text
    if kind == "group":
        return value in text or "Cooperativa " + value.removeprefix("coop_") in text
    if kind == "comuni":
        return sum(c in text for c in value) >= 3
    if kind == "number":
        return any(abs(x - value) <= expected.get("tolerance", 0) for x in numbers(text))
    if kind == "step":
        label = next(s.label.it for s in PATHWAY.steps if s.id == value)
        return value in text or label.lower() in text.lower()
    if kind == "yes_no":
        first = re.sub(r"^[^\wÀ-ÿ]+", "", text).split()[0].strip(".,:;!«»\"'“”").lower() if text else ""
        return first == ("sì" if value else "no") or (value and first == "si")
    raise ValueError(f"unknown expected type {kind}")


def passes(score: int, asked: int) -> bool:
    return score >= math.ceil(PASS_SHARE * asked)


def run(scenarios, live: bool, runs_dir: Path, only: dict[int, tuple[str, ...]] | None = None) -> dict:
    # --live fills what the cache lacks (cache_first, warm-up timeout); answers already cached are replayed
    llm.configure(**({"mode": "cache_first", "timeout_s": llm.WARMUP_TIMEOUT_S} if live else {"mode": "cache_only"}))
    questions = json.loads((BENCHMARK / "questions.json").read_text(encoding="utf-8"))
    out = {"prompt_version": investigator.ASK_VERSION, "day": DAY, "scenarios": {}}
    for n in scenarios:
        ctx = tools.Context.for_run(f"s{n}_baseline", runs_dir, day=DAY)
        try:
            facilities = ctx.db.rows("SELECT name, type, asst_id FROM facilities ORDER BY facility_id")
            answers = []
            for i, q in enumerate(questions["scenarios"][str(n)], 1):
                if only and q["id"] not in only.get(n, ()):
                    continue
                started = time.perf_counter()
                try:
                    inv = investigator.ask(ctx, PATHWAY, DAY, q["question"], f"bench_s{n}_{i}", facilities)
                    conclusion, steps = inv.conclusion["it"], [{"tool": s["tool"], "args": s["args"]} for s in inv.steps]
                    claims = [c["text"]["it"] for c in inv.claims]
                except llm.LLMUnavailable as e:
                    conclusion, steps, claims = f"(nessuna risposta: {e})", [], []
                ok = correct(q["expected"], conclusion)
                answers.append({"id": q["id"], "correct": ok, "expected": q["expected"], "conclusion": conclusion,
                                "claims": claims, "steps": steps, "seconds": round(time.perf_counter() - started)})
                print(f"s{n} {q['id']:<32} {'OK ' if ok else 'NO '} {conclusion[:110]}", flush=True)
            score = sum(a["correct"] for a in answers)
            out["scenarios"][str(n)] = {"correct": score, "passed": passes(score, len(answers)), "answers": answers}
            print(f"scenario {n}: {score} of {len(answers)}", flush=True)
        finally:
            ctx.close()
    return out


def main(argv: list[str]) -> None:
    ids = [a for a in argv if a.startswith("q")]
    trial = bool(ids) or any(a.isdigit() for a in argv)
    scenarios = [int(a) for a in argv if a.isdigit()] or (list(SCENARIOS) if ids else list(DEMO))
    only = {n: tuple(ids) for n in scenarios} if ids else (None if trial else DEMO)
    with tempfile.TemporaryDirectory() as tmp:
        build_runs(Path(tmp), scenarios)
        out = run(scenarios, "--live" in argv, Path(tmp), only)
    if trial:  # a trial of some scenarios or questions is not a benchmark result
        return
    path = BENCHMARK / f"results_{investigator.ASK_VERSION}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
