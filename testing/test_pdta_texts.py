"""PDTA texts (delivery plan step 1.8) stay consistent with the pathway model and across languages."""

import re
from pathlib import Path

import pytest

from engine.pathway import load

PDTA = Path(__file__).resolve().parents[1] / "spec" / "pdta"
HF_IT = (PDTA / "hf_lombardia_v1.it.md").read_text(encoding="utf-8")
LABELS_IT = {"telemon": "Telemonitoraggio", "cardio_visit": "Visita cardiologica", "echo": "Ecocardiogramma",
             "lab_bnp": "BNP"}


def line_with(text: str, label: str) -> str:
    return next(line for line in text.splitlines() if line.lstrip().startswith(tuple("123456789")) and label in line)


def test_hf_text_has_every_step_with_its_deadline():
    pathway = load("hf_lombardia_v1")
    for step in pathway.steps:
        if step.id == "discharge":
            continue
        line = line_with(HF_IT, LABELS_IT[step.id])
        days = step.due_days or step.every_days
        assert f"{days} giorni" in line, (step.id, line)
        for code in (step.codes or []) + (step.loinc or []):
            assert code in line, (step.id, code)


def test_hf_text_has_the_codes_rules_thresholds_and_escalation():
    p = load("hf_lombardia_v1")
    for code in p.eligibility.any_diagnosis + p.eligibility.any_drug_atc:
        assert code in HF_IT
    assert "2 kg o più in 3 giorni" in HF_IT  # weight_gain rule
    assert "entro 7 giorni" in HF_IT
    assert "da 30 giorni" in HF_IT  # no_dispense('C03CA01', 30)
    t, e = p.status_thresholds, p.escalation
    assert f"entro {t.due_soon_days} giorni" in HF_IT
    assert f"supera i {t.dropped_after_days} giorni" in HF_IT
    assert f"{t.dropped_if_overdue_steps} o più tappe" in HF_IT
    assert f"Dopo {e.call_after_days} giorni" in HF_IT
    assert f"Dopo {e.mmg_after_days} giorni" in HF_IT
    for ward in p.ward_by_diagnosis["428.*"]:
        assert ward.replace("_", " ") in HF_IT


@pytest.mark.parametrize("name", ["hf_lombardia_v1", "t2d_lombardia_v1"])
def test_italian_and_english_versions_carry_the_same_numbers_and_codes(name):
    # The header notes differ on purpose (the English one names its Italian source); compare the bodies.
    body = lambda text: "\n".join(line for line in text.splitlines() if not line.startswith((">", "#")))
    numbers = lambda text: sorted(re.findall(r"\d+(?:[.*-]\d*)*\*?", body(text)))
    it = (PDTA / f"{name}.it.md").read_text(encoding="utf-8")
    en = (PDTA / f"{name}.en.md").read_text(encoding="utf-8")
    assert numbers(it) == numbers(en)
