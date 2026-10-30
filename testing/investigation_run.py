"""Investigator on the real runs (delivery plan steps 2.9, 2.17 and 2.30): each scenario's agents arm is
simulated to the day of its echo alarm; on each regional alarm's tick the Investigator runs
(engine.investigations), and every stored investigation is scored. Testing code, so it may read demo/truth/; the agent never does.

    uv run python testing/investigation_run.py [1 2 3] [--live]

--live calls the model for every answer the cache lacks and stores it in demo/cache/ (warm-up: about 5 minutes
per investigation on the team laptops, D12, and each scenario has its group alarms' investigations before the
echo's); without it the investigation is replayed from the cache and a miss leaves no
investigation. Results go to testing/results/ (not committed).
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from agents import investigator, llm, tools
from engine import queries
from engine.db import tool_cursor
from engine.tick import Population, Run
from sim.truth import TRUTH_DIR

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LAST_ALARM_DAY = 60  # every scenario's echo alarm opens by day 33 (SPEC §5.3)


def run_to_alarm(scenario: int, population: Population, runs_dir: Path) -> tuple[Run, list[dict], float]:
    """The agents arm of `scenario` advanced to the day its first wait alarm opens (a facility's echo): the
    run, the messages of every regional alarm opened until then, the wait alarm last (group alarms, C26,
    open earlier), and the seconds the wait alarm's tick took (its investigation is part of it)."""
    run = Run(f"s{scenario}_agents", population, runs_dir, days=LAST_ALARM_DAY + 1)
    alarms = []
    while run.day < LAST_ALARM_DAY:
        started = time.perf_counter()
        regional = [m for m in run.tick() if m["type"] == "alert" and m["payload"]["level"] == "regional"]
        alarms += sorted(regional, key=lambda m: m["payload"]["facility_id"] is not None)
        if any(m["payload"]["facility_id"] for m in regional):
            return run, alarms, round(time.perf_counter() - started, 1)
    raise AssertionError(f"scenario {scenario}: no wait alarm by day {LAST_ALARM_DAY}")


def stored(run: Run, alarm: dict) -> dict | None:
    """The investigation the tick stored for the alarm, each step with its tool's result again: the row keeps
    tool and arguments only, and a call repeated on the same day gives the same bytes (C5, C7)."""
    found = [i for i in queries.investigations(run.con) if i["investigation_id"] == alarm["payload"]["investigation_id"]]
    if not found:
        return None
    inv = found[0]
    with tool_cursor(run.con) as cur:
        ctx = tools.Context(run.run_id, tools.Query(cur), run.day)
        for s in inv["steps"]:
            s["result"] = tools.call(ctx, s["tool"], s["args"])
    return inv


def pattern_1(inv: dict, scenario: int, facility_names: dict[str, str]) -> dict:
    """AC1, pattern 1: a claim names the bottleneck hospital and rests on wait_by_hospital, and a claim names
    the hospital with free capacity and rests on free_slots that show free slots there."""
    truth = json.loads((TRUTH_DIR / f"scenario_{scenario}.json").read_text(encoding="utf-8"))
    bottleneck = facility_names[truth["echo_bottleneck"]["facility_id"]]
    free = facility_names[truth["echo_free_capacity"]["facility_id"]]
    steps = {s["step"]: s for s in inv["steps"]}
    cited = [(c["text"]["it"], steps[c["step"]]) for c in inv["claims"]]
    wait = any(s["tool"] == "wait_by_hospital" and bottleneck in text for text, s in cited)
    slots = any(s["tool"] == "free_slots" and free in text and (s["result"].get("data") or {}).get(free, 0) > 0
                for text, s in cited)
    return {"bottleneck": bottleneck, "free_capacity": free, "names_bottleneck": wait, "names_free_capacity": slots,
            "found": wait and slots}


def _cited(inv: dict, tool: str, measure: str, grouping: str | None = None) -> list[tuple[str, dict]]:
    """(Italian text, step) of the claims resting on `tool` with this measure (and grouping)."""
    steps = {s["step"]: s for s in inv["steps"]}
    default = {"adherence_by_group": "dispensing", "adherence_by_area": "telemonitoring"}[tool]
    return [(c["text"]["it"], steps[c["step"]]) for c in inv["claims"]
            if steps[c["step"]]["tool"] == tool and steps[c["step"]]["args"].get("grouping") == grouping
            and steps[c["step"]]["args"].get("measure", default) == measure]


def pattern_2(inv: dict, scenario: int) -> dict:
    """AC1, pattern 2: a claim on dispensing by MMG group names the hidden cooperative (coop_6 or Cooperativa 6)."""
    truth = json.loads((TRUTH_DIR / f"scenario_{scenario}.json").read_text(encoding="utf-8"))
    coop = truth["low_adherence_group"]["coop_id"]
    names = (coop, "Cooperativa " + coop.removeprefix("coop_"))
    found = any(any(n in text for n in names) for text, _ in _cited(inv, "adherence_by_group", "dispensing", "mmg_group"))
    return {"group": coop, "found": found}


def pattern_3(inv: dict, scenario: int) -> dict:
    """AC1, pattern 3: claims on telemonitoring by comune or by area name at least half of the hidden comuni,
    the rule of the data-side proof (sim.pattern_proof.compare)."""
    truth = json.loads((TRUTH_DIR / f"scenario_{scenario}.json").read_text(encoding="utf-8"))
    comuni = truth["rural_dropout_comuni"]
    cited = (_cited(inv, "adherence_by_group", "telemonitoring", "comune")
             + _cited(inv, "adherence_by_area", "telemonitoring"))
    # every comune the cited tools returned and a claim names; more than half must be hidden ones
    returned = set()
    for _, s in cited:
        data = s["result"].get("data") or {}
        returned |= ({c for a in data["areas"] for c in a["comuni"]} if "areas" in data
                     else set(data) - {"rest_of_ats"})
    named = sorted(c for c in returned if any(c in text for text, _ in cited))
    hits = sorted(set(named) & set(comuni))
    return {"comuni": comuni, "named": named, "found": len(hits) * 2 >= len(comuni) and len(hits) * 2 > len(named)}


def main(argv: list[str]) -> None:
    live = "--live" in argv
    scenarios = [int(a) for a in argv if a.isdigit()] or [1, 2, 3]
    # --live fills what the cache lacks: `cache_first` with the warm-up timeout; `live` would ask again for
    # every answer, cached or not (step 2.10: it re-ran all nine investigations to re-warm three)
    llm.configure(**({"mode": "cache_first", "timeout_s": llm.WARMUP_TIMEOUT_S} if live else {"mode": "cache_only"}))
    population = Population()
    RESULTS_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for n in scenarios:
            run, alarms, seconds = run_to_alarm(n, population, Path(tmp))
            try:
                names = dict(run.con.execute("SELECT facility_id, name FROM facilities").fetchall())
                invs = [(alarm, stored(run, alarm)) for alarm in alarms]
            finally:
                run.close()
            saved = []
            for alarm, inv in invs:
                print(f"\nscenario {n}, day {alarm['day']}: {alarm['payload']['text']['it']}")
                if inv is None:
                    print("  no investigation (see the log): a cache miss in cache_only, or no answer from the model")
                    continue
                for s in inv["steps"]:
                    print(f"  {s['step']}. {s['tool']} {json.dumps(s['args'], ensure_ascii=False)} -> "
                          f"{s['result_summary']['it']}")
                for c in inv["claims"]:
                    print(f"  [{c['step']}] {c['text']['it']}")
                print(f"  => {inv['conclusion']['it']}")
                scores = {"pattern_1": pattern_1(inv, n, names), "pattern_2": pattern_2(inv, n),
                          "pattern_3": pattern_3(inv, n)}
                for name, score in scores.items():
                    print(f"  {name} {'FOUND' if score['found'] else 'not found'}: {score}", flush=True)
                saved.append({"day": alarm["day"], "alarm": alarm["payload"]["text"], **scores,
                              "steps": [{k: v for k, v in s.items() if k != "result"} for s in inv["steps"]],
                              "claims": inv["claims"], "conclusion": inv["conclusion"]})
            print(f"  wait alarm's tick {seconds} s", flush=True)
            out = RESULTS_DIR / f"investigation_s{n}_{investigator.PROMPT_VERSION}.json"
            out.write_text(json.dumps({"scenario": n, "tick_seconds": seconds, "investigations": saved},
                                      indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
