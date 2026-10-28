"""Maria's recorded story (step 2.1, D35) is her baseline run to day 62."""

from engine import story


def test_story_file_is_current(fixture_scenario):
    # Regenerate with: uv run python -m engine.story
    # The fixture builder runs the same baseline to day 62 with its own loop, so equal bytes also show that
    # the tick (engine.tick.Run) produces what the batch loop produces.
    _, files = fixture_scenario
    for patient_id, run_id, day in story.STORIES:
        assert story.path(patient_id, run_id, day).read_text(encoding="utf-8") == \
            files[f"api/patient_{patient_id}_{run_id}.json"]
