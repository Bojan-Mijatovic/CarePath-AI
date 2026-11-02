"""PNE forecast to year end (delivery plan step 2.6, C35): the numbers step 7 shows come from engine.pne, read
from the what-if grid's runs, which go on to the year's last day."""

import json

import pytest

from engine import pathway as pathway_model
from engine import pne, whatif

HF = pathway_model.load("hf_lombardia_v1")
SCENARIOS = (1, 2, 3)


def grid(n: int) -> dict:
    return json.loads(whatif.path(n).read_text(encoding="utf-8"))


@pytest.mark.parametrize("n", SCENARIOS)
def test_every_run_reaches_the_year_end(n):
    for r in grid(n)["runs"]:
        y = r["year_end"]
        assert y["day"] == whatif.YEAR_END_DAY
        assert 0 < y["readmission_rate_30d"] < 1
        # the year counts at least the readmissions of the 6 months, which start after day 0
        assert y["readmissions_30d"] >= r["readmissions"]


@pytest.mark.parametrize("n", SCENARIOS)
def test_the_forecast_is_the_grid_s_year_end(n):
    g = grid(n)
    by = {(r["arm"], (r["levers"] or {}).get("extra_slots", 0)): r for r in g["runs"]}
    for k in range(whatif.MAX_EXTRA_SLOTS + 1):
        f = pne.forecast(g, k, HF)
        assert f["day"] == whatif.YEAR_END_DAY
        assert f["baseline"]["readmission_rate_30d"] == by["baseline", 0]["year_end"]["readmission_rate_30d"]
        assert f["agents"]["readmission_rate_30d"] == by["agents", 0]["year_end"]["readmission_rate_30d"]
        assert f["lever"]["readmission_rate_30d"] == by["agents", k]["year_end"]["readmission_rate_30d"]
        assert f["reference"] == HF.readmission_reference.model_dump()


@pytest.mark.parametrize("n", SCENARIOS)
def test_the_agents_lower_the_year_end_rate(n):
    f = pne.forecast(grid(n), 0, HF)
    assert f["agents"]["readmission_rate_30d"] < f["baseline"]["readmission_rate_30d"]


def test_post_whatif_carries_the_forecast():
    """What POST /api/whatif returns for step 7 (the API passes the pathway on screen)."""
    out = whatif.result(2, whatif.Levers(extra_slots=1), pathway=HF)
    assert out["pne"] == pne.forecast(grid(2), 1, HF)
    assert "year_end" not in out["lever"]  # the summaries stay as in C27
    assert "pne" not in whatif.result(2, whatif.Levers(extra_slots=1))
