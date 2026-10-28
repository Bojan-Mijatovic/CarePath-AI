"""Fixture mode of the API (delivery plan step 1.25): the SPEC §10 endpoints answered from testing/fixtures/.

The console's first screens are built on the committed fixtures (step 1.23) through the same paths and
messages the real API will serve, so step 2.1 (tick) and 2.16 onward swap the source, not the screens.
The fixtures hold scenario 2 only, whatever envelope is chosen, and the stream replays them from the
demo's start day (D21) to their last day, once per connection.
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "testing" / "fixtures"
START_DAY = 23  # the demo opens on day 23 (delivery plan D21)
STREAM_ORDER = ("tick", "alert", "action", "investigation")


class Fixtures:
    def __init__(self, directory: Path = FIXTURES_DIR):
        self.dir = directory

    def _read(self, path: str):
        file = self.dir / path
        return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None

    def kpi(self, run: str, pathway_id: str | None, level: str | None, key: str | None) -> list[dict]:
        rows = {(r["day"], r["pathway_id"], r["level"], r["key"]): r
                for path in (f"api/kpi_ats_{run}.json", f"api/kpi_{run}_day62.json") for r in self._read(path) or []}
        return [r for _, r in sorted(rows.items())
                if (pathway_id is None or r["pathway_id"] == pathway_id) and (level is None or r["level"] == level)
                and (key is None or r["key"] == key)]

    def patient(self, patient_id: str, run: str) -> dict | None:
        return self._read(f"api/patient_{patient_id}_{run}.json")

    def actions(self, run: str, status: str | None) -> list[dict]:
        return [a for a in self._read(f"api/actions_{run}.json") or [] if status is None or a["status"] == status]

    def stream(self, run: str = "s2_agents") -> list[dict]:
        """Every message from START_DAY on, in day order and SPEC §9 tick order within a day."""
        tick = self._read("stream/tick.json")
        msgs = [{**tick, "day": r["day"], "payload": {**tick["payload"], "kpi": {
                    k: v for k, v in r.items() if k not in ("day", "level", "key")}}}
                for r in self.kpi(run, None, "ats", "ats")]
        for name in ("alert_patient.json", "alert_regional.json", "investigation.json"):
            m = self._read(f"stream/{name}")
            msgs += m if isinstance(m, list) else [m]
        msgs += [{"type": "action", "scenario": tick["scenario"], "day": a["created_day"], "payload": a}
                 for a in self.actions(run, None)]
        msgs = [m for m in msgs if m["day"] >= START_DAY]
        return sorted(msgs, key=lambda m: (m["day"], STREAM_ORDER.index(m["type"])))
