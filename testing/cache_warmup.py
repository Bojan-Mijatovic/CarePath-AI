"""Cache warm-up and completeness check (delivery plan step 2.11, SPEC §8, C10): plays the LLM outputs the demo
shows, listed in demo/cache/manifest.json (D17), through the API: all runs to the start day, then for each
scenario in demo order a jump to its alarm day, its alarm investigations, and its Chiedi questions.

    uv run python testing/cache_warmup.py [--live]

--live fills what the cache lacks (cache_first with the warm-up timeout, about 5–7 minutes an investigation);
without it the play is cache_only and prints every miss. testing/test_cache_complete.py runs the same play.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from agents import llm
from api.main import create_app
from engine.tick import Demo

MANIFEST = Path(__file__).resolve().parents[1] / "demo" / "cache" / "manifest.json"
READY_S = 300  # the start replay of every run (9 with the lever runs, step 2.28) takes about 70 s ...
WARM_READY_S = 3600  # ... and in a warm-up it also runs the investigations of alarms before the start day


def play(runs_dir: Path, ui_dir: Path, ready_s: int = READY_S) -> dict:
    """{scenario: {"investigations": [rows of the alarm day and before], "answers": [(question, status,
    seconds, row or detail)], "proposals": [capacity_proposal rows]}} for the manifest, in its order, with
    the gateway as it is configured."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    (ui_dir / "index.html").write_text("<title>CarePath AI</title>", encoding="utf-8")
    out = {}
    # Without the lever runs (step 2.28): they show no LLM text, and their group alarms' investigations have
    # keys of their own (the run id is in the tools' results), so a warm-up with them would fill six more. The
    # proposed levers stay: the agents arm proposes one on its alarm day (step 2.27).
    demo = Demo(runs_dir, lever_runs=False)
    with TestClient(create_app(demo=demo, tick_seconds=0.05, ui_dir=ui_dir)) as c:
        deadline = time.monotonic() + ready_s
        while c.get("/api/kpi").status_code == 503:
            assert time.monotonic() < deadline, f"the demo runs were not ready in {ready_s} s"
            time.sleep(0.5)
        for s in manifest["scenarios"]:
            n = s["scenario"]
            c.post(f"/api/sim/scenario/{n}").raise_for_status()
            c.post(f"/api/sim/jump/{s['alarm_day']}").raise_for_status()
            found = [i for i in c.get("/api/investigations", params={"run": f"s{n}_agents"}).json()
                     if i["day"] <= s["alarm_day"]]
            answers = []
            for q in s["questions"]:
                started = time.perf_counter()
                r = c.post("/api/ask", json={"question": q})
                answers.append((q, r.status_code, round(time.perf_counter() - started, 2),
                                r.json() if r.status_code == 200 else r.text))
            proposals = [a for a in c.get("/api/actions", params={"run": f"s{n}_agents"}).json()
                         if a["type"] == "capacity_proposal"]
            # The operator's actions of demo/SCRIPT.md on the alarm day, in its order: approve the proposal, then
            # (scenario 2, steps 5b and 6) the MMG notice and Riprogrammazione at "Da sola". They change the run
            # from the next day, so a later cached text (the day-59 report) must be warmed after them (C41)
            for p in proposals:
                c.post(f"/api/actions/{p['action_id']}/approve").raise_for_status()
            if n == manifest["scenarios"][0]["scenario"]:
                for a in c.get("/api/actions", params={"run": f"s{n}_agents", "status": "proposed"}).json():
                    if a["type"] == "notify_mmg":
                        c.post(f"/api/actions/{a['action_id']}/approve").raise_for_status()
                c.put("/api/settings/autonomy", json={"type": "reschedule", "level": 3}).raise_for_status()
            for day in s.get("report_days", []):  # step 2.14: after the questions, which are keyed by the alarm day
                # the days before it from the cache only: alarms on the way (scenario 2, days 35 and 49) are not
                # in the demo, and a warm-up must not ask the model to investigate them (D17)
                mode = llm.mode()
                llm.set_mode("cache_only")
                c.post(f"/api/sim/jump/{day - 1}").raise_for_status()
                llm.set_mode(mode)
                c.post(f"/api/sim/jump/{day}").raise_for_status()
            reports = [r for r in c.get("/api/reports", params={"run": f"s{n}_agents"}).json()
                       if r["day"] in s.get("report_days", [])]
            out[n] = {"investigations": found, "answers": answers, "proposals": proposals, "reports": reports}
    return out


def misses(played: dict) -> list[str]:
    """What the demo would not show: an alarm investigation the manifest counts but the run lacks, or a
    question without an answer, or a capacity proposal in the template's words where the manifest lists the
    model's (step 2.27)."""
    expected = {s["scenario"]: s for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]}
    out = []
    for n, got in played.items():
        if len(got["investigations"]) != expected[n]["alarm_investigations"]:
            out.append(f"scenario {n}: {len(got['investigations'])} alarm investigations, "
                       f"{expected[n]['alarm_investigations']} expected")
        if expected[n].get("capacity_proposal") and [p["payload"].get("wording") for p in got["proposals"]] != ["model"]:
            out.append(f"scenario {n}: capacity proposal {[p['payload']['wording'] for p in got['proposals']]}, "
                       "one in the model's words expected")
        wording = {r["day"]: r["wording"] for r in got["reports"]}
        out += [f"scenario {n}: report of day {d} {wording.get(d, 'missing')}, the model's words expected"
                for d in expected[n].get("report_days", []) if wording.get(d) != "model"]
        out += [f"scenario {n}: no answer to {q!r} ({status})" for q, status, _, _ in got["answers"] if status != 200]
    return out


def main(argv: list[str]) -> None:
    live = "--live" in argv
    llm.configure(**({"mode": "cache_first", "timeout_s": llm.WARMUP_TIMEOUT_S} if live else {"mode": "cache_only"}))
    with tempfile.TemporaryDirectory() as tmp:
        played = play(Path(tmp) / "runs", Path(tmp), WARM_READY_S if live else READY_S)
    for n, got in played.items():
        for i in got["investigations"]:
            print(f"s{n} day {i['day']:>2} {i['investigation_id']:<18} {i['conclusion']['it'][:100]}")
        for q, status, seconds, answer in got["answers"]:
            text = answer["conclusion"]["it"] if status == 200 else answer
            print(f"s{n} ask {status} {seconds:>6} s  {q[:60]} -> {str(text)[:120]}")
        for p in got["proposals"]:
            print(f"s{n} day {p['created_day']:>2} capacity_proposal ({p['payload']['wording']}): {p['rationale']['it']}")
        for r in got["reports"]:
            print(f"s{n} day {r['day']:>2} report ({r['wording']}):\n{r['text']['it']}\n{r['text']['en']}")
    print("\n".join(misses(played)) or "no miss")


if __name__ == "__main__":
    main(sys.argv[1:])
