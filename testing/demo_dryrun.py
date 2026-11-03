"""A technical rehearsal of the demo (phase 4, ahead of AC9's human runs): the real API walks demo/SCRIPT.md N times
in a row, with a reset between runs, and every check of what the screen would show is logged.

    uv run python testing/demo_dryrun.py [N]        # default 10; about 3 minutes a run

Each run, from the reset to day 23: scenario 2 at ×1 to its alarm (the investigation is there and the Verifier
marked its steps), Chiedi's prepared questions (answered from the cache), the capacity proposal in the model's
words, approved, the MMG notice approved, Riprogrammazione at "Da sola", ×4 to day 62, the lever run caught up,
the day-59 report in the model's words, what-if with the PNE forecast and euros, the call list, Maria and her bed
(step 9c, Bed Finder on her day-47 admission without CarePath); then
scenarios 1 and 3 (investigation, proposal, ×4) and the reveal, where every pattern must match. A failed check
or an HTTP error is a stop. The log goes to testing/results/ (not committed). It needs no model: the demo runs
in cache_only (D14).
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8002/api"
RESULTS = Path(__file__).resolve().parent / "results"


class Stop(Exception):
    """What would stop the demo: an error, a missing investigation, a clock that does not move."""


FALLBACKS: list[str] = []  # what the demo survives on its fallback: a template, a question without a prepared answer


def req(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(r, timeout=600) as f:
            return json.loads(f.read())
    except urllib.error.HTTPError as e:
        raise Stop(f"{method} {path}: HTTP {e.code} {e.read()[:200]!r}") from None


def check(ok: bool, what: str) -> None:
    if not ok:
        raise Stop(what)


def run_until(scenario: int, target: int, speed: int) -> float:
    req("POST", "/sim/speed", {"factor": speed})
    t = time.perf_counter()
    while req("POST", f"/sim/scenario/{scenario}")["day"] < target:
        time.sleep(0.5)
        check(time.perf_counter() - t < 300, f"scenario {scenario} did not reach day {target} in 5 min")
    req("POST", "/sim/pause")
    return time.perf_counter() - t


def caught_up(run_id: str, target: int) -> float:
    t = time.perf_counter()
    while req("GET", f"/kpi?run={urllib.parse.quote(run_id)}&level=ats")[-1]["day"] < target:
        time.sleep(0.5)
        check(time.perf_counter() - t < 300, f"{run_id} did not catch up to day {target} in 5 min")
    return time.perf_counter() - t


def proposal(n: int) -> dict:
    found = [a for a in req("GET", f"/actions?run=s{n}_agents&status=proposed") if a["type"] == "capacity_proposal"]
    check(len(found) == 1, f"scenario {n}: {len(found)} capacity proposals waiting, one expected")
    if found[0]["payload"]["wording"] != "model":
        FALLBACKS.append(f"scenario {n}: the proposal in the template's words")
    return found[0]


def alarm_investigation(n: int, day: int) -> dict:
    invs = [i for i in req("GET", f"/investigations?run=s{n}_agents") if i["day"] == day and i["alert_id"]]
    check(len(invs) == 1, f"scenario {n}: no investigation of the day-{day} alarm (a cache miss?)")
    check(all(c.get("verified") is not None for c in invs[0]["claims"]), f"scenario {n}: claims without the Verifier's mark")
    return invs[0]


def one_run() -> dict:
    times: dict[str, float] = {}
    t = time.perf_counter()
    status = req("POST", "/sim/reset")
    times["reset"] = time.perf_counter() - t
    check(status["day"] == 23 and status["scenario"] == 2, f"after the reset: {status}, not scenario 2 on day 23")
    check(req("GET", "/sim/cache")["mode"] == "cache_only", "the gateway is not in cache_only")

    times["s2_to_alarm"] = run_until(2, 33, 1)
    alarm_investigation(2, 33)
    day = req("POST", "/sim/scenario/2")["day"]
    times["s2_alarm_paused_on"] = day
    for q in req("GET", "/questions")["questions"]:
        try:
            answer = req("POST", "/ask", {"question": q})
            check(bool(answer["claims"]), f"no claim in the answer to {q!r}")
        except Stop as e:
            if "503" not in str(e):
                raise
            FALLBACKS.append(f"day {day}: no prepared answer to {q[:40]!r}…")
    p = proposal(2)
    req("POST", f"/actions/{p['action_id']}/approve")
    for a in req("GET", "/actions?run=s2_agents&status=proposed"):
        if a["type"] == "notify_mmg":
            req("POST", f"/actions/{a['action_id']}/approve")
    req("PUT", "/settings/autonomy", {"type": "reschedule", "level": 3})
    times["s2_x4_to_62"] = run_until(2, 62, 4)
    times["s2_catch_up"] = caught_up(p["payload"]["lever_run"], req("POST", "/sim/scenario/2")["day"])
    reports = {r["day"]: r for r in req("GET", "/reports?run=s2_agents")}
    check(59 in reports, "no day-59 report")
    if reports[59]["wording"] != "model":
        FALLBACKS.append("the day-59 report in the template's words")
    w = req("POST", "/whatif", {"levers": {"extra_slots": 1}})
    check("pne" in w and w.get("saving_eur", 0) > 0, "what-if without the PNE forecast or the saving")
    check(len(req("GET", "/worklist")) > 0, "an empty call list")
    check(bool(req("GET", "/patients/p_00001?run=s2_agents")["timeline"]), "Maria without a timeline")
    # Step 9c (optional, D64): Bed Finder for Maria's day-47 admission without CarePath
    t = time.perf_counter()
    bed = req("POST", "/admissions", {"patient_id": "p_00001", "run": "s2_baseline", "day": 47})["action"]
    times["s2_bed"] = time.perf_counter() - t
    check(bed is not None and bed["status"] == "executed", f"no bed assigned to Maria: {bed}")

    for n, alarm in ((1, 19), (3, 29)):
        req("POST", f"/sim/scenario/{n}")
        if alarm > 23:
            times[f"s{n}_to_alarm"] = run_until(n, alarm, 1)
        alarm_investigation(n, alarm)
        p = proposal(n)
        req("POST", f"/actions/{p['action_id']}/approve")
        start = req("POST", f"/sim/scenario/{n}")["day"]
        times[f"s{n}_x4"] = run_until(n, start + 20, 4)
        times[f"s{n}_catch_up"] = caught_up(p["payload"]["lever_run"], req("POST", f"/sim/scenario/{n}")["day"])

    for n in (2, 1, 3):
        r = req("GET", f"/reveal/{n}")
        check(all(r[p]["match"] for p in ("bottleneck", "mmg_group", "rural_comuni")), f"reveal of scenario {n}: {r}")
    return {k_: round(v, 1) for k_, v in times.items()}


def server_gb(pid: int) -> float | None:
    """The API's memory after a run, to see a leak across resets (psutil if installed: `uv run --with psutil`)."""
    try:
        import psutil
    except ImportError:
        return None
    p = psutil.Process(pid)
    return round(sum(c.memory_info().rss for c in [p, *p.children(recursive=True)]) / 2**30, 2)


def main(argv: list[str]) -> int:
    n = int(argv[0]) if argv else 10
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"demo_dryrun_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    server_log = out.with_suffix(".server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8002",
                               "--log-level", "warning"], stdout=server_log, stderr=subprocess.STDOUT)
    stops = 0
    try:
        t = time.perf_counter()
        while True:
            try:
                req("GET", "/kpi?level=ats")
                break
            except (Stop, urllib.error.URLError, ConnectionError):
                time.sleep(1)
                if time.perf_counter() - t > 600:
                    raise SystemExit("the API was not ready in 10 min")
        with out.open("w", encoding="utf-8") as log:
            for k in range(1, n + 1):
                started = time.perf_counter()
                FALLBACKS.clear()
                try:
                    times, error = one_run(), None
                except Stop as e:
                    times, error = {}, str(e)
                    stops += 1
                row = {"run": k, "ok": error is None, "error": error, "fallbacks": list(FALLBACKS),
                       "minutes": round((time.perf_counter() - started) / 60, 1), "times": times,
                       "server_gb": server_gb(server.pid)}
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
                log.flush()
                print(f"run {k}: {'ok' if error is None else 'STOP: ' + error} ({row['minutes']} min, server "
                      f"{row['server_gb']} GB) fallbacks {FALLBACKS} {times}", flush=True)
    finally:
        server.terminate()
        server.wait(30)
        server_log.close()
    print(f"{n - stops} of {n} runs without a stop; log: {out}")
    return 1 if stops else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
