"""Cache completeness check (SPEC §8, C10; delivery plan step 2.11): the demo's LLM outputs, listed in
demo/cache/manifest.json (D17), play through the API in cache_only with no miss. Runs after every change to the
simulator, the engine, the tools or the prompts, and before every rehearsal; a miss is filled with
`uv run python testing/cache_warmup.py --live`.
"""

import json

import pytest

import cache_warmup


@pytest.mark.demo
def test_the_demo_plays_from_the_cache(demo_played):
    assert not cache_warmup.misses(demo_played)


@pytest.mark.demo
def test_alarm_investigations_are_on_their_alarm_day(demo_played):
    """Each scenario's echo investigation is on its alarm day and the group alarms' on day 0 (C26), so the
    manifest's days are the ones the demo jumps to."""
    for s in json.loads(cache_warmup.MANIFEST.read_text(encoding="utf-8"))["scenarios"]:
        days = sorted(i["day"] for i in demo_played[s["scenario"]]["investigations"])
        assert days == [0, 0, s["alarm_day"]], (s["scenario"], days)
