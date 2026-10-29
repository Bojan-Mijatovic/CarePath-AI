"""Investigator on the real runs (delivery plan step 2.9): each scenario's agents arm is simulated to the day
of its regional alarm, and the Investigator looks for its cause. Testing code, so it may read demo/truth/ to
score the answer; the agent never does.

    uv run python testing/investigation_run.py [1 2 3] [--live]

--live calls the model and stores every answer in demo/cache/ (warm-up: about 4 minutes per scenario on the
team laptops, D12); without it the investigation is replayed from the cache and a miss is an error.
Results go to testing/results/ (not committed).
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from agents import investigator, llm, tools
from engine.db import tool_cursor
from engine.tick import Population, Run
from sim.truth import TRUTH_DIR

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LAST_ALARM_DAY = 60  # every scenario's echo alarm opens by day 33 (SPEC §5.3)


def run_to_alarm(scenario: int, population: Population, runs_dir: Path) -> tuple[Run, dict]:
    """The agents arm of `scenario` advanced to the day its first regional alarm opens; the alarm's message."""
    run = Run(f"s{scenario}_agents", population, runs_dir, days=LAST_ALARM_DAY + 1)
    while run.day < LAST_ALARM_DAY:
        regional = [m for m in run.tick() if m["type"] == "alert" and m["payload"]["level"] == "regional"]
        if regional:
            return run, regional[0]
    raise AssertionError(f"scenario {scenario}: no regional alarm by day {LAST_ALARM_DAY}")


def investigate(run: Run, alarm: dict, pathway) -> investigator.Investigation:
    facilities = run.con.execute("SELECT name, type, asst_id FROM facilities ORDER BY facility_id").fetchall()
    (step,) = run.con.execute("SELECT step FROM alerts WHERE level = 'regional' AND day = $d AND facility_id = $f",
                              {"d": run.day, "f": alarm["payload"]["facility_id"]}).fetchone()
    with tool_cursor(run.con) as cur:
        ctx = tools.Context(run.run_id, tools.Query(cur), run.day)
        return investigator.investigate(ctx, pathway, run.day, alarm["payload"]["text"], step, f"inv_{run.run_id}_1",
                                        facilities)


def pattern_1(inv: investigator.Investigation, scenario: int, facility_names: dict[str, str]) -> dict:
    """AC1, pattern 1: a claim names the bottleneck hospital and rests on wait_by_hospital, and a claim names
    the hospital with free capacity and rests on free_slots that show free slots there."""
    truth = json.loads((TRUTH_DIR / f"scenario_{scenario}.json").read_text(encoding="utf-8"))
    bottleneck = facility_names[truth["echo_bottleneck"]["facility_id"]]
    free = facility_names[truth["echo_free_capacity"]["facility_id"]]
    steps = {s["step"]: s for s in inv.steps}
    cited = [(c["text"]["it"], steps[c["step"]]) for c in inv.claims]
    wait = any(s["tool"] == "wait_by_hospital" and bottleneck in text for text, s in cited)
    slots = any(s["tool"] == "free_slots" and free in text and (s["result"].get("data") or {}).get(free, 0) > 0
                for text, s in cited)
    return {"bottleneck": bottleneck, "free_capacity": free, "names_bottleneck": wait, "names_free_capacity": slots,
            "found": wait and slots}


def main(argv: list[str]) -> None:
    live = "--live" in argv
    scenarios = [int(a) for a in argv if a.isdigit()] or [1, 2, 3]
    llm.configure(mode="live" if live else "cache_only")
    population = Population()
    RESULTS_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for n in scenarios:
            run, alarm = run_to_alarm(n, population, Path(tmp))
            try:
                names = dict(run.con.execute("SELECT facility_id, name FROM facilities").fetchall())
                started = time.perf_counter()
                inv = investigate(run, alarm, population.pathway)
                seconds = round(time.perf_counter() - started, 1)
                score = pattern_1(inv, n, names)
            finally:
                run.close()
            print(f"\nscenario {n}, day {inv.day}: {alarm['payload']['text']['it']}")
            for s in inv.steps:
                print(f"  {s['step']}. {s['tool']} {json.dumps(s['args'], ensure_ascii=False)} -> {s['result_summary']['it']}")
            for c in inv.claims:
                print(f"  [{c['step']}] {c['text']['it']}")
            print(f"  => {inv.conclusion['it']}")
            print(f"  pattern 1 {'FOUND' if score['found'] else 'NOT FOUND'}: {score}; {seconds} s", flush=True)
            out = RESULTS_DIR / f"investigation_s{n}_{investigator.PROMPT_VERSION}.json"
            out.write_text(json.dumps({"scenario": n, "seconds": seconds, "pattern_1": score, "question": inv.question,
                                       "steps": [{k: v for k, v in s.items() if k != "result"} for s in inv.steps],
                                       "claims": inv.claims, "conclusion": inv.conclusion},
                                      indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
