import pytest

from fixtures import scenario


def pytest_collection_modifyitems(items):
    """Timers first, on a laptop that has not been working for minutes, as in the demo, where the tick starts
    after a pause on day 23 (D21). Step 2.22: right after AC1's three runs, AC2's both-arms p95 went from
    about 300 to 655-686 ms; in a process of its own it stays near 300."""
    items.sort(key=lambda item: item.get_closest_marker("timing") is None)  # stable: keeps the order otherwise


@pytest.fixture(scope="session")
def demo_played(tmp_path_factory):
    """The manifest's demo outputs played through the API in cache_only (step 2.11, testing/cache_warmup.py),
    for the cache completeness check (C10) and AC5. About 2 minutes."""
    import cache_warmup
    from agents import llm

    llm.configure(mode="cache_only", log_path=None)
    try:
        return cache_warmup.play(tmp_path_factory.mktemp("demo_runs"), tmp_path_factory.mktemp("demo_ui"))
    finally:
        llm.configure()


@pytest.fixture(scope="session")
def fixture_scenario(tmp_path_factory):
    """The fixture scenario of step 1.23: (directory with s2_baseline and s2_agents run databases,
    {path under testing/fixtures/: JSON text}). Built once per test session, in about 15 s."""
    runs = tmp_path_factory.mktemp("fixture_runs")
    return runs, scenario.build(runs)
