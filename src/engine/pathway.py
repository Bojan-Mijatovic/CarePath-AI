"""Pathway model: a PDTA as configuration (spec/SPEC.md §4). Delivery plan step 1.3.

The Pydantic model below is the single definition. `spec/pathways/pathway.schema.json` is generated
from it, and a test fails if the two drift apart. Everything that loads or emits a pathway (engine,
simulator, Pathway Builder, Rule Advisor) validates through `Pathway.model_validate`, which also checks
the rule language of SPEC §4: anything outside that grammar is rejected before activation.

    uv run python -m engine.pathway   # rewrite spec/pathways/pathway.schema.json
"""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PATHWAYS_DIR = Path(__file__).resolve().parents[2] / "spec" / "pathways"
SCHEMA_PATH = PATHWAYS_DIR / "pathway.schema.json"

ID = r"^[a-z][a-z0-9_]*$"
EventType = Literal["DISCHARGE", "ADMISSION", "VISIT", "IMAGING", "LAB", "DISPENSE", "TELEMON_START",
                    "TELEMON_READING", "BOOKING", "CALL", "REMINDER"]  # SPEC §3.1

# Rule language, SPEC §4. A condition is one or more clauses joined by " and ".
FEATURES = ("weight_gain_kg_3d", "days_since_last_reading", "age", "distance_km", "risk_score")
OP = r"(>=|>|<=|<|==)"
NUM = r"-?\d+(\.\d+)?"
ATC = r"'[A-Z]\d{2}[A-Z]{2}\d{2}'"
OVERDUE = re.compile(r"^overdue\('(?P<step>[a-z][a-z0-9_]*)', \d+\)$")
CLAUSES = [
    re.compile(rf"^({'|'.join(FEATURES)}) {OP} {NUM}$"),
    re.compile(rf"^days_since_last_dispense\({ATC}\) {OP} {NUM}$"),
    re.compile(rf"^no_dispense\({ATC}, \d+\)$"),
    OVERDUE,
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Bilingual(Strict):
    """A name the console and the worklist show (SPEC §2 language rule)."""
    it: str = Field(min_length=1)
    en: str = Field(min_length=1)


class Eligibility(Strict):
    any_diagnosis: list[str] = Field(default_factory=list, description="ICD-9-CM codes; a trailing * matches a prefix")
    any_drug_atc: list[str] = Field(default_factory=list, description="ATC codes")
    drug_names: dict[str, Bilingual] = Field(default_factory=dict, description="name of each drug in any_drug_atc")

    @model_validator(mode="after")
    def not_empty(self):
        if not (self.any_diagnosis or self.any_drug_atc):
            raise ValueError("eligibility needs at least one diagnosis or drug")
        if set(self.drug_names) != set(self.any_drug_atc):
            raise ValueError("drug_names needs exactly one name for each drug of any_drug_atc")
        return self


class StatusThresholds(Strict):
    due_soon_days: int = Field(gt=0)
    dropped_after_days: int = Field(gt=0)
    dropped_if_overdue_steps: int = Field(ge=1)


class Step(Strict):
    id: str = Field(pattern=ID)
    label: Bilingual
    event: EventType
    codes: list[str] | None = Field(None, description="ICD-9-CM or procedure codes")
    specialty: str | None = None
    loinc: list[str] | None = None
    service: str | None = Field(None, pattern=ID, description="capacity service it is booked in: capacity_slots.service and the BOOKING code")
    max_wait_days: int | None = Field(None, gt=0, description="regional alarm when a facility's mean wait for the service is longer")
    due_days: int | None = Field(None, gt=0, description="due this many days after the `after` step")
    after: str | None = Field(None, pattern=ID)
    every_days: int | None = Field(None, gt=0, description="repeats with this period")

    @model_validator(mode="after")
    def timing(self):
        if (self.due_days is None) != (self.after is None):
            raise ValueError(f"step {self.id}: due_days and after go together")
        if self.every_days is not None and self.due_days is not None:
            raise ValueError(f"step {self.id}: use either due_days/after or every_days")
        if self.max_wait_days is not None and self.service is None:
            raise ValueError(f"step {self.id}: max_wait_days needs a service, or there is no wait to measure")
        return self


class Then(Strict):
    step: str | None = Field(None, pattern=ID)
    due_days: int | None = Field(None, gt=0)
    flag: str | None = Field(None, pattern=ID)

    @model_validator(mode="after")
    def one_action(self):
        if not ((self.step is not None and self.due_days is not None and self.flag is None)
                or (self.flag is not None and self.step is None and self.due_days is None)):
            raise ValueError('then is {"step", "due_days"} or {"flag"}')
        return self


class Rule(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    id: str = Field(pattern=ID)
    condition: str = Field(alias="if", description="rule language of SPEC §4")
    then: Then

    @model_validator(mode="after")
    def grammar(self):
        for clause in self.condition.split(" and "):
            if not any(p.match(clause) for p in CLAUSES):
                raise ValueError(f"rule {self.id}: {clause!r} is outside the rule language")
        return self

    def referenced_steps(self) -> set[str]:
        refs = {m["step"] for c in self.condition.split(" and ") if (m := OVERDUE.match(c))}
        return refs | ({self.then.step} if self.then.step else set())


class Escalation(Strict):
    reminder_day: int = Field(ge=0)
    call_after_days: int = Field(gt=0)
    mmg_after_days: int = Field(gt=0)
    high_risk_skips_reminder: bool


class Reference(Strict):
    rate: float = Field(gt=0, lt=1, description="published 30-day readmission rate, a fraction")
    label: Bilingual = Field(description="where the rate comes from, for example Italia, PNE 2025")


class Pathway(Strict):
    pathway_id: str = Field(pattern=ID)
    name: str = Field(description="Italian name of the PDTA document")
    label: Bilingual = Field(description="the pathway as the console names it, for example in the top bar")
    readmission_reference: Reference | None = Field(None, description="a published rate the console shows next to the run's")
    eligibility: Eligibility
    status_thresholds: StatusThresholds
    steps: list[Step] = Field(min_length=1)
    rules: list[Rule] = Field(default_factory=list)
    escalation: Escalation
    ward_by_diagnosis: dict[str, list[str]] = Field(default_factory=dict, description="Bed Finder, optional layer")

    @model_validator(mode="after")
    def references(self):
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        services = [s.service for s in self.steps if s.service]
        if len(services) != len(set(services)):
            raise ValueError("a service can belong to one step only, or a BOOKING could not be told apart")
        for i, s in enumerate(self.steps):
            if s.after is not None and s.after not in ids[:i]:
                raise ValueError(f"step {s.id}: after={s.after!r} must name an earlier step")
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("rule ids must be unique")
        for r in self.rules:
            unknown = r.referenced_steps() - set(ids)
            if unknown:
                raise ValueError(f"rule {r.id}: unknown steps {sorted(unknown)}")
        return self


def load(pathway_id: str, directory: Path = PATHWAYS_DIR) -> Pathway:
    return Pathway.model_validate_json((directory / f"{pathway_id}.json").read_text(encoding="utf-8"))


def schema_text() -> str:
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "pathway.schema.json",
              **Pathway.model_json_schema(by_alias=True)}
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    SCHEMA_PATH.write_text(schema_text(), encoding="utf-8", newline="\n")
    print(SCHEMA_PATH)


if __name__ == "__main__":
    main()
