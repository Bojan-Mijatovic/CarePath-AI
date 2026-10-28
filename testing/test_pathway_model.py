import copy
import json

import jsonschema
import pytest
from pydantic import ValidationError

from engine.pathway import PATHWAYS_DIR, SCHEMA_PATH, Pathway, load, schema_text

HF = json.loads((PATHWAYS_DIR / "hf_lombardia_v1.json").read_text(encoding="utf-8"))


def test_hf_pathway_validates_against_the_schema():
    p = load("hf_lombardia_v1")  # delivery plan step 1.3 "done when"
    assert p.pathway_id == "hf_lombardia_v1"
    assert [s.id for s in p.steps] == ["discharge", "telemon", "cardio_visit", "echo", "lab_bnp"]
    assert {s.id: s.due_days for s in p.steps if s.due_days} == {"telemon": 7, "cardio_visit": 30, "echo": 90}


def test_round_trip_keeps_the_if_key():
    dumped = load("hf_lombardia_v1").model_dump(exclude_none=True)
    assert dumped["rules"][0]["if"] == "weight_gain_kg_3d >= 2"
    assert Pathway.model_validate(dumped) == load("hf_lombardia_v1")


def test_committed_schema_matches_the_model():
    # Regenerate with: uv run python -m engine.pathway
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_hf_pathway_validates_with_a_plain_json_schema_validator():
    # Consumers outside our Python code see only pathway.schema.json; it must accept the file on its own.
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(HF, schema, cls=jsonschema.Draft202012Validator)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(edited(lambda p: p["steps"][0].update({"event": "PHONE"})), schema,
                            cls=jsonschema.Draft202012Validator)


def edited(change):
    p = copy.deepcopy(HF)
    change(p)
    return p


@pytest.mark.parametrize("condition", [
    "weight_gain_kg_3d >= 2",
    "days_since_last_reading > 3 and age >= 75",
    "days_since_last_dispense('C03CA01') > 30",
    "no_dispense('C03CA01', 30)",
    "overdue('echo', 14) and distance_km > 40",
    "risk_score >= 0.7",
])
def test_rule_language_accepts_the_spec_grammar(condition):
    Pathway.model_validate(edited(lambda p: p["rules"][0].update({"if": condition})))


@pytest.mark.parametrize("condition", [
    "weight_gain_kg_3d >= two",                # not a number
    "systolic_bp > 140",                       # unknown feature
    "age >= 75 or distance_km > 40",           # only "and" joins clauses
    "no_dispense(C03CA01, 30)",                # ATC must be quoted
    "__import__('os').system('x')",            # anything else
    "risk_score >= 0.7 and",                   # dangling join
])
def test_rule_language_rejects_everything_else(condition):
    with pytest.raises(ValidationError, match="outside the rule language"):
        Pathway.model_validate(edited(lambda p: p["rules"][0].update({"if": condition})))


@pytest.mark.parametrize("change, message", [
    (lambda p: p["rules"][0].update({"if": "overdue('ecg', 7)"}), "unknown steps"),
    (lambda p: p["rules"][0]["then"].update({"step": "ecg"}), "unknown steps"),
    (lambda p: p["steps"][1].update({"after": "echo"}), "earlier step"),
    (lambda p: p["steps"].append(dict(p["steps"][1])), "step ids must be unique"),
    (lambda p: p["steps"][3].update({"service": "cardio_visit"}), "one step only"),
    (lambda p: p["steps"][1].pop("after"), "due_days and after go together"),
    (lambda p: p["steps"][4].update({"due_days": 5, "after": "discharge"}), "either due_days/after or every_days"),
    (lambda p: p["steps"][0].update({"event": "PHONE"}), "Input should be"),
    (lambda p: p["rules"][1].update({"then": {"flag": "x", "step": "echo", "due_days": 3}}), "then is"),
    (lambda p: p.update({"eligibility": {}}), "at least one diagnosis or drug"),
    (lambda p: p.update({"colour": "red"}), "Extra inputs are not permitted"),
])
def test_invalid_pathways_are_rejected(change, message):
    with pytest.raises(ValidationError, match=message):
        Pathway.model_validate(edited(change))
