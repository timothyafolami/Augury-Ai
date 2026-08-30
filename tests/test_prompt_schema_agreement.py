"""A prompt that describes a field the schema does not have produces nothing.

This is not hypothetical. The analyst prompt asked for a `claim` field that did
not exist and never described `prediction`, the field that actually carries
falsifiability. The model complied with the prompt, the schema dropped the
answer, and the arm scored zero against a baseline scoring 1.000. Nothing
failed loudly; it just quietly did not work.
"""

import re

import pytest
from pydantic import BaseModel

from augury.agents.triage import TriageDecision
from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport
from augury.prompts import raw

# The prompt and the schema its answer is validated against.
CONTRACTS = [
    ("baseline", DraftFinding, DraftPrediction),
    ("analyst", DraftFinding, DraftPrediction),
    ("triage", TriageDecision, None),
]


def described_fields(prompt: str) -> set[str]:
    """Field names the prompt asks for.

    A bullet may name several at once (``- `path`, `line`, `symbol`: where it
    is``), which describes all three, so every backticked name before the colon
    counts.
    """
    fields: set[str] = set()
    for bullet in re.findall(r"^\s*-\s+(`\w+`(?:\s*,\s*`\w+`)*)\s*:", prompt, re.MULTILINE):
        fields |= set(re.findall(r"`(\w+)`", bullet))
    return fields


@pytest.mark.parametrize(("name", "schema", "nested"), CONTRACTS)
def test_a_prompt_never_asks_for_a_field_the_schema_lacks(
    name: str, schema: type[BaseModel], nested: type[BaseModel] | None
) -> None:
    known = set(schema.model_fields) | (set(nested.model_fields) if nested else set())
    asked = described_fields(raw(name))

    assert asked <= known, (
        f"{name}.md asks for {sorted(asked - known)}, which {schema.__name__} "
        "does not have; the model will comply and the answer will be discarded"
    )


@pytest.mark.parametrize(("name", "schema", "nested"), CONTRACTS)
def test_a_prompt_describes_every_field_the_schema_requires(
    name: str, schema: type[BaseModel], nested: type[BaseModel] | None
) -> None:
    """A field the model is never told about is a field it fills badly or not
    at all, and `prediction` is the one that decides the headline metric.

    The nested schema is checked too. It was accepted as a parameter here and
    never used, so deleting every `metric`/`comparator`/`unit` bullet from a
    prompt left the suite green -- and the baseline prompt was already in
    exactly that state, describing all six prediction sub-fields in one line of
    prose with no examples and no unit vocabulary.
    """
    asked = described_fields(raw(name))
    required = set(schema.model_fields)
    if nested is not None:
        required |= set(nested.model_fields)
    missing = required - asked

    assert not missing, f"{name}.md never describes {sorted(missing)}"


@pytest.mark.parametrize("name", ["analyst", "baseline"])
def test_both_arms_are_told_what_a_vacuous_prediction_is(name: str) -> None:
    """The validator rejects those, and a rejection the model could have
    avoided is a wasted call.

    Parametrised over both arms. Asserting it for the analyst alone did not
    merely miss the asymmetry -- it institutionalised it, since a rejected
    prediction lands in the falsifiable-precision denominator and only one arm
    was told how to avoid one.
    """
    prompt = raw(name).lower()

    # The gate's rules, not one phrasing of them: it rejects a threshold below
    # what its unit can measure, a ceiling above it, and a band too wide to
    # exclude anything. A test pinned to a sentence goes stale the moment the
    # rule is stated better, and stale here means one arm quietly loses the
    # explanation.
    assert "at least 1" in prompt, "the unit floor"
    assert "hundredfold" in prompt, "the widest honest band"
    assert "greater than `value`" in prompt, "which bound is which"


def test_draft_report_is_covered_by_the_finding_contracts() -> None:
    assert set(DraftReport.model_fields) == {"findings"}
