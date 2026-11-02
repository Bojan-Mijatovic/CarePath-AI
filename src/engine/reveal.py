"""Rivelazione (demo step 10, delivery plan step 2.20, SPEC §10 `GET /reveal/{scenario}`, C37).

What the agents raised by themselves, next to where the scenario hid its problems. The first side is read from
the agents arm's own alarms, which Monitoring opened from the data (SPEC §5.3): the first wait alarm's facility
and its ASST, the MMG group of the group alarm on `adherence_by_group`, and the text of the one on
`adherence_by_area`, which names the area's comuni. The second side is `scenario_truth` (demo/truth/), which
only this screen and the tests read (CLAUDE.md rule 5); agent code never comes here. A match is code comparing
the two.
"""

import json

import duckdb

from engine.pathway import Pathway
from sim.truth import TRUTH_DIR


def reveal(con: duckdb.DuckDBPyConnection, pathway: Pathway, scenario: int) -> dict:
    truth = json.loads((TRUTH_DIR / f"scenario_{scenario}.json").read_text(encoding="utf-8"))
    facilities = {f: (name, asst) for f, name, asst in con.execute("SELECT facility_id, name, asst_id FROM facilities").fetchall()}
    tool_of = {g.id: g.tool for g in pathway.group_alarms}
    alarms = con.execute("""
        SELECT day, facility_id, group_alarm, group_key, text FROM alerts
        WHERE level = 'regional' AND pathway_id = $pw ORDER BY day, alert_id""", {"pw": pathway.pathway_id}).fetchall()
    wait = next(((d, f) for d, f, *_ in alarms if f is not None), None)
    group = lambda tool: next(((d, k, json.loads(t)) for d, _, g, k, t in alarms if g and tool_of.get(g) == tool), None)
    mmg, area = group("adherence_by_group"), group("adherence_by_area")

    hidden_facility = truth["echo_bottleneck"]["facility_id"]
    comuni = truth["rural_dropout_comuni"]
    named = [c for c in comuni if area and c in area[2]["it"]]
    return {
        "scenario": scenario,
        "bottleneck": {
            "found": {"day": wait[0], "facility": facilities[wait[1]][0], "asst_id": facilities[wait[1]][1]} if wait else None,
            "hidden": {"facility": facilities[hidden_facility][0], "asst_id": truth["echo_bottleneck"]["asst_id"]},
            "match": bool(wait) and wait[1] == hidden_facility},
        "mmg_group": {
            "found": {"day": mmg[0], "group": mmg[1], "text": mmg[2]} if mmg else None,
            "hidden": {"group": truth["low_adherence_group"]["coop_id"]},
            "match": bool(mmg) and mmg[1] == truth["low_adherence_group"]["coop_id"]},
        "rural_comuni": {
            "found": {"day": area[0], "text": area[2]} if area else None,
            "hidden": {"comuni": comuni, "named": named},
            # as AC1's data-side proof (sim.pattern_proof): at least half of the hidden comuni named
            "match": 2 * len(named) >= len(comuni)},
    }
