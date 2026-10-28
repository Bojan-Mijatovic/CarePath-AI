"""Risk model (delivery plan step 2.3, SPEC C19)."""

import hashlib
import json

import numpy as np
import pytest

from engine import pathway as pathway_model
from engine import risk
from engine.tick import SEED, Population, Run

PW = "hf_lombardia_v1"


@pytest.fixture(scope="module")
def maria_run(tmp_path_factory):
    """Scenario 2 baseline to day 43, the day Maria's weight has risen 2 kg in 3 days."""
    run = Run("s2_baseline", Population(), tmp_path_factory.mktemp("risk_runs"), days=60)
    run.advance_to(43)
    yield run
    run.close()


def test_features_are_named_from_the_pathway():
    hf = pathway_model.load(PW)
    names = risk.feature_names(hf)
    assert "days_since_last_dispense:C03CA01" in names
    other = hf.model_copy(update={"eligibility": hf.eligibility.model_copy(update={"any_drug_atc": ["A10BA02", "C09AA05"]})})
    assert [n for n in risk.feature_names(other) if n.startswith("days_since_last_dispense")] == [
        "days_since_last_dispense:A10BA02", "days_since_last_dispense:C09AA05"]


def test_model_file_matches_the_code():
    m = risk.RiskModel(pathway_model.load(PW))
    attrs = m.booster.attributes()
    assert json.loads(attrs["features"]) == m.names
    assert int(attrs["train_seed"]) == risk.TRAIN_SEED != SEED  # never trained on the demo's seed
    assert int(attrs["horizon_days"]) == risk.HORIZON_DAYS == 30


def test_weight_gain_follows_the_rule_language(maria_run):
    # Maria reads 72.2 kg on day 40 and 74.3 kg on day 43 (demo/story/): the weight_gain rule fires on day 43.
    assert maria_run.state.weight_gain_kg_3d(43)[0] == pytest.approx(2.1)


def test_scores_and_drivers_on_a_tick(maria_run):
    m = maria_run.risk
    assert m.risk is not None
    assert 0 <= m.risk.min() <= m.risk.max() <= 1
    assert np.array_equal(m.risk, m.risk.round(4))  # SPEC §2
    rows = maria_run.con.execute("SELECT risk_score, risk_drivers FROM pathway_state").fetchall()
    assert all(len(d) <= risk.TOP_DRIVERS and set(d) <= set(m.names) for _, d in rows)
    high = sum(score >= risk.HIGH_RISK for score, _ in rows)
    assert 50 <= high <= 250  # about 1% of 10,000 (D37)
    assert m.update(maria_run.con, maria_run.state, 43) == 0  # the same day again changes nothing


def test_scores_are_the_same_on_a_second_run(maria_run, tmp_path):
    again = Run("s2_baseline", Population(), tmp_path, days=60)
    try:
        again.advance_to(43)
        assert np.array_equal(again.risk.risk, maria_run.risk.risk)
    finally:
        again.close()


def test_committed_model_is_current(tmp_path):
    # Retrain with: uv run python -m engine.risk (about 30 s; the bytes are the same every time)
    hf = pathway_model.load(PW)
    path = tmp_path / "risk.json"
    risk.train(hf, risk.dataset(risk.TRAIN_SEED, None, hf)).save_model(path)
    committed = risk.MODELS_DIR / f"risk_{PW}.json"
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(committed.read_bytes()).digest()
