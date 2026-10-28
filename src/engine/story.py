"""Maria's story without CarePath (demo step 1), recorded in advance (delivery plan step 2.1, D35).

The demo opens with every run on day 23 (D21), but the story tells what happens to Maria up to her
readmission on day 47. So the baseline arm of scenario 2 is run once to day 62 and her Paziente 360 is
written to demo/story/; GET /api/patients/p_00001?run=s2_baseline&day=62 serves that file (SPEC §10, C17).
Maria is scripted (AC14), so the file is the same for every scenario. testing/test_story.py checks that it
is current.

    uv run python -m engine.story
"""

import json
import shutil
import tempfile
from pathlib import Path

from engine import queries
from engine.tick import Population, Run

STORY_DIR = Path(__file__).resolve().parents[2] / "demo" / "story"
STORIES = [("p_00001", "s2_baseline", 62)]  # (patient, run, day)


def path(patient_id: str, run_id: str, day: int, story_dir: Path = STORY_DIR) -> Path:
    return story_dir / f"{patient_id}_{run_id}_day{day}.json"


def load(patient_id: str, run_id: str, day: int, story_dir: Path = STORY_DIR) -> dict | None:
    file = path(patient_id, run_id, day, story_dir)
    return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None


def text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build(runs_dir: Path, population: Population | None = None) -> dict[str, str]:
    """{file name: JSON text} for every story."""
    population = population or Population()
    out = {}
    for patient_id, run_id, day in STORIES:
        run = Run(run_id, population, runs_dir)
        try:
            run.advance_to(day)
            with run.con.cursor() as cur:
                out[path(patient_id, run_id, day).name] = text(queries.patient_360(cur, patient_id))
        finally:
            run.close()
    return out


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        files = build(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    STORY_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (STORY_DIR / name).write_text(content, encoding="utf-8", newline="\n")
        print(STORY_DIR / name)


if __name__ == "__main__":
    main()
