"""`scenario_truth`: where each envelope hides its patterns (SPEC §3.3). Delivery plan step 1.18.

Derived from src/sim/scenarios/*.json and written outside every run database, to demo/truth/. Only the
acceptance tests (AC1, AC13) and the Rivelazione screen read it; agent tools cannot (engine.db.connect_for_tools).

    uv run python -m sim.truth   # rewrite demo/truth/scenario_<n>.json
"""

import json
from pathlib import Path

from sim.population import load_reference
from sim.step import load_scenario

TRUTH_DIR = Path(__file__).resolve().parents[2] / "demo" / "truth"
SCENARIOS = (1, 2, 3)


def truth(n: int, ref: dict | None = None) -> dict:
    ref = ref or load_reference()
    sc = load_scenario(n)
    asst = ref["facilities"].set_index("facility_id").asst_id
    names = ref["comuni"].set_index("comune_istat").name
    return {
        "scenario": sc.scenario,
        "echo_bottleneck": {"facility_id": sc.echo_bottleneck.facility_id,
                            "asst_id": asst[sc.echo_bottleneck.facility_id]},
        "echo_free_capacity": {"facility_id": sc.echo_free_capacity.facility_id},
        "rural_dropout_comuni": [names[c] for c in sc.rural_dropout.comuni],
        "low_adherence_group": {"coop_id": sc.low_adherence.coop_id},
    }


def text(n: int, ref: dict | None = None) -> str:
    return json.dumps(truth(n, ref), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    ref = load_reference()
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    for n in SCENARIOS:
        path = TRUTH_DIR / f"scenario_{n}.json"
        path.write_text(text(n, ref), encoding="utf-8", newline="\n")
        print(path)


if __name__ == "__main__":
    main()
