"""Benchmark: 10 questions per scenario with expected answers (delivery plan step 1.24, AC6 in step 2.10).

The questions are what the audience may pick in Chiedi (Solution Plan §12), asked on day 35 (the
Chiedi step, D21) of each scenario's baseline arm. Every expected answer comes from one or two calls of
agents.tools, the same calls an Investigator can make, so each question is answerable with the tools alone;
`calls` lists them. Questions 8–10 have the answer "no": a hospital, an MMG group and a comune where
nothing is wrong, so the benchmark also shows that agents do not find patterns that are not there. Their
subjects are chosen from the scenario file (a place without the pattern), never named in a prompt.

testing/test_benchmark.py rebuilds the runs, checks questions.json against this script, and checks the
pattern answers against demo/truth.

    uv run python testing/benchmark/questions.py   # rewrite testing/benchmark/questions.json
"""

import json
import shutil
import tempfile
from pathlib import Path

import duckdb

from agents import tools
from sim.run import run
from sim.step import load_scenario

BENCHMARK = Path(__file__).resolve().parent
DAY, PATHWAY_ID, SCENARIOS = 35, "hf_lombardia_v1", (1, 2, 3)
# "Yes" thresholds of the yes/no questions, stated with the answer so the scorer and a reader see them.
WAIT_RATIO, DISPENSING_GAP, TELEMON_GAP = 2.0, -0.05, -0.10


def it_num(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def pct(x: float) -> tuple[str, str]:
    return it_num(100 * x) + "%", f"{100 * x:.1f}%"


class Asker:
    def __init__(self, ctx: tools.Context):
        self.ctx, self.calls = ctx, []

    def __call__(self, name: str, **args) -> dict:
        result = tools.call(self.ctx, name, {"pathway_id": PATHWAY_ID, **args} if name != "free_slots" else args)
        assert "data" in result, result
        self.calls.append(result["source"] | {"day": None, "run_id": None})
        return result["data"]


def subjects(n: int, con: duckdb.DuckDBPyConnection) -> dict:
    """Places without a pattern in scenario n: the third hospital, the median MMG group, the largest comune
    outside the rural cluster."""
    sc = load_scenario(n)
    hospitals = [r[0] for r in con.execute("SELECT facility_id FROM facilities WHERE type = 'hospital' ORDER BY 1").fetchall()]
    third = next(h for h in hospitals if h not in (sc.echo_bottleneck.facility_id, sc.echo_free_capacity.facility_id))
    coops = [r[0] for r in con.execute("""
        SELECT m.coop_id FROM patients p JOIN mmg m USING (mmg_id) WHERE m.coop_id <> $low
        GROUP BY 1 ORDER BY count(*) DESC, 1""", {"low": sc.low_adherence.coop_id}).fetchall()]
    comune = con.execute("""
        SELECT p.comune_istat, c.name FROM patients p JOIN comuni c USING (comune_istat)
        WHERE NOT list_contains($rural, p.comune_istat) GROUP BY ALL ORDER BY count(*) DESC, 1 LIMIT 1""",
                         {"rural": sc.rural_dropout.comuni}).fetchall()[0]
    names = dict(con.execute("SELECT facility_id, name FROM facilities").fetchall())
    return {"hospital": names[third], "coop": coops[len(coops) // 2], "comune": comune}


def questions(n: int, runs_dir: Path) -> list[dict]:
    ctx = tools.Context.for_run(f"s{n}_baseline", runs_dir, day=DAY)
    try:
        s = subjects(n, ctx.db.con)
        out = []

        def q(qid, it, en, kind, value, answer_it, answer_en, ask, **extra):
            out.append({"id": qid, "question": {"it": it, "en": en}, "expected": {"type": kind, "value": value, **extra},
                        "answer": {"it": answer_it, "en": answer_en}, "calls": ask.calls})

        a = Asker(ctx)
        w = a("wait_by_hospital", step="echo", period_days=7)
        top = max(w, key=w.get)
        q("q01_echo_wait", "Quale ospedale ha l'attesa più lunga per l'ecocardiogramma nell'ultima settimana?",
          "Which hospital has the longest wait for an echocardiogram in the last week?", "facility", top,
          f"{top}: {it_num(w[top])} giorni in media dalla prenotazione all'esame.",
          f"{top}: {w[top]:.1f} days on average from booking to exam.", a)

        a = Asker(ctx)
        f = a("free_slots", service="echo")
        most = max(f, key=f.get)
        q("q02_echo_free", "Dove ci sono più posti liberi per l'ecocardiogramma nelle prossime tre settimane?",
          "Where are the most free echocardiogram slots in the next three weeks?", "facility", most,
          f"{most}: {f[most]} posti liberi.", f"{most}: {f[most]} free slots.", a)

        a = Asker(ctx)
        g = a("adherence_by_group", grouping="mmg_group", measure="dispensing")
        low = next(iter(g))
        q("q03_low_dispensing_group", "Quale gruppo di MMG ha la quota più bassa di pazienti che ritirano il furosemide?",
          "Which MMG group has the lowest share of patients collecting furosemide?", "group", low,
          f"{low}: {pct(g[low])[0]} contro {pct(g['rest_of_ats'])[0]} nel resto dell'ATS.",
          f"{low}: {pct(g[low])[1]} against {pct(g['rest_of_ats'])[1]} in the rest of the ATS.", a)

        a = Asker(ctx)
        t = a("adherence_by_group", grouping="comune", measure="telemonitoring")
        worst = [c for c in t if c != "rest_of_ats"][:5]
        q("q04_telemonitoring_comuni",
          "In quali comuni i pazienti smettono più spesso di inviare le letture del telemonitoraggio?",
          "In which comuni do patients most often stop sending telemonitoring readings?", "comuni", worst,
          f"{', '.join(worst)}; nel resto dell'ATS invia letture il {pct(t['rest_of_ats'])[0]}.",
          f"{', '.join(worst)}; in the rest of the ATS {pct(t['rest_of_ats'])[1]} send readings.", a, top_k=5)

        a = Asker(ctx)
        r = a("compare_segments", a={}, b={}, metric="readmission_rate_30d")["a"]
        q("q05_readmission_rate", "Qual è il tasso di riammissione a 30 giorni negli ultimi sei mesi in tutta l'ATS?",
          "What is the 30-day readmission rate over the last six months across the ATS?", "number", r,
          f"{pct(r)[0]}.", f"{pct(r)[1]}.", a, tolerance=0.005)

        a = Asker(ctx)
        o = a("patients_overdue", step="echo")["count"]
        q("q06_echo_overdue", "Quanti pazienti hanno l'ecocardiogramma in ritardo?",
          "How many patients are overdue for their echocardiogram?", "number", o,
          f"{o} pazienti.", f"{o} patients.", a, tolerance=0)

        a = Asker(ctx)
        c = {k: v for k, v in a("compliance_by_step").items() if v is not None}
        step = min(c, key=c.get)
        q("q07_worst_step", "Quale step del percorso viene rispettato in tempo meno spesso?",
          "Which pathway step is least often done on time?", "step", step,
          f"{step}: {pct(c[step])[0]} delle scadenze rispettate negli ultimi 90 giorni.",
          f"{step}: {pct(c[step])[1]} of deadlines met in the last 90 days.", a)

        a = Asker(ctx)
        w = a("wait_by_hospital", step="echo", period_days=7)
        h = s["hospital"]
        median = sorted(w.values())[len(w) // 2]  # one bottleneck must not lift the yardstick
        q("q08_no_echo_problem", f"L'{h} ha un problema di attese per l'ecocardiogramma rispetto agli altri ospedali?",
          f"Does {h} have an echocardiogram waiting problem compared with the other hospitals?", "yes_no",
          w[h] > WAIT_RATIO * median,
          f"No: {it_num(w[h])} giorni; la mediana degli ospedali è {it_num(median)}.",
          f"No: {w[h]:.1f} days; the median across hospitals is {median:.1f}.", a,
          rule=f"yes when the wait is more than {WAIT_RATIO} times the median of all hospitals")

        a = Asker(ctx)
        d = a("compare_segments", a={"coop_id": s["coop"]}, b={}, metric="dispensing")
        q("q09_no_dispensing_problem", f"I pazienti del gruppo di MMG {s['coop']} ritirano il furosemide meno degli altri?",
          f"Do the patients of MMG group {s['coop']} collect furosemide less than the others?", "yes_no",
          d["difference"] < DISPENSING_GAP,
          f"No: {pct(d['a'])[0]} contro {pct(d['b'])[0]} in tutta l'ATS.",
          f"No: {pct(d['a'])[1]} against {pct(d['b'])[1]} across the ATS.", a,
          rule=f"yes when the difference is below {DISPENSING_GAP}")

        a = Asker(ctx)
        code, name = s["comune"]
        t = a("compare_segments", a={"comune_istat": [code]}, b={}, metric="telemonitoring")
        q("q10_no_telemonitoring_problem", f"A {name} i pazienti smettono il telemonitoraggio più che nel resto dell'ATS?",
          f"Do patients in {name} stop telemonitoring more than in the rest of the ATS?", "yes_no",
          t["difference"] < TELEMON_GAP,
          f"No: invia letture il {pct(t['a'])[0]}, contro il {pct(t['b'])[0]} in tutta l'ATS.",
          f"No: {pct(t['a'])[1]} send readings, against {pct(t['b'])[1]} across the ATS.", a,
          rule=f"yes when the difference is below {TELEMON_GAP}")
        return out
    finally:
        ctx.close()


def build_runs(runs_dir: Path) -> None:
    """Each scenario's baseline arm up to the benchmark day, so capacity_slots is the state of that day."""
    for n in SCENARIOS:
        run(f"s{n}_baseline", days=DAY + 1, runs_dir=runs_dir)


def text(runs_dir: Path) -> str:
    doc = {"day": DAY, "pathway_id": PATHWAY_ID, "arm": "baseline",
           "scenarios": {str(n): questions(n, runs_dir) for n in SCENARIOS}}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        build_runs(tmp)
        (BENCHMARK / "questions.json").write_text(text(tmp), encoding="utf-8", newline="\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(BENCHMARK / "questions.json")


if __name__ == "__main__":
    main()
