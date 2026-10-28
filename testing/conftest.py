import pytest

from fixtures import scenario


@pytest.fixture(scope="session")
def fixture_scenario(tmp_path_factory):
    """The fixture scenario of step 1.23: (directory with s2_baseline and s2_agents run databases,
    {path under testing/fixtures/: JSON text}). Built once per test session, in about 15 s."""
    runs = tmp_path_factory.mktemp("fixture_runs")
    return runs, scenario.build(runs)
