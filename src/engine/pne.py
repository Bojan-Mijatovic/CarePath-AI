"""PNE forecast to year end (delivery plan step 2.6, SPEC §5.2, C35): the pathway's 30-day readmission rate
on the year's last day, without CarePath, with CarePath, and with CarePath and the what-if lever.

The PNE indicator (Agenas) is readmissions within 30 days over index discharges in a calendar year; here the
demo's year, day 0 to what-if's YEAR_END_DAY, as kpi_daily counts it (SPEC §5.2). Its year-end value comes
from the what-if grid's full runs, which go on to that day after their 6 months (D48): the same seed and the
same code, so the "forecast" is the simulation's own future, not a fitted trend. The runs use the default
autonomy levels; a manager who raises one in the demo takes the live run away from them, and the screen says
the forecast is precomputed. The line to compare with is the pathway's published reference (C23); there is
no ATS target in the data, so none is shown.
"""

from engine.pathway import Pathway
from engine.whatif import YEAR_END_DAY


def forecast(grid: dict, extra_slots: int, pathway: Pathway) -> dict:
    """{day, baseline, agents, lever, reference} from one scenario's grid: each arm's year-end
    {readmissions_30d, readmission_rate_30d}, and the pathway's reference or None. KeyError for a grid
    computed before the runs went on to year end (compute it again)."""
    runs = {(r["arm"], (r["levers"] or {}).get("extra_slots", 0)): r for r in grid["runs"]}
    year_end = lambda key: {k: runs[key]["year_end"][k] for k in ("readmissions_30d", "readmission_rate_30d")}
    reference = pathway.readmission_reference
    return {"day": YEAR_END_DAY, "baseline": year_end(("baseline", 0)), "agents": year_end(("agents", 0)),
            "lever": year_end(("agents", extra_slots)),
            "reference": reference.model_dump() if reference else None}
