"""Parity in the instructions, not only in the bytes of the corpus.

`test_arm_parity.py` checks that both prompts contain certain substrings. It
passes on a prompt that says "ignore the condition", and it passed while the
baseline was told to omit a required field, was never told what the validator
rejects, and was handed deployment configuration shaped exactly like source.

An unfair baseline does not produce a wrong number in one column. It produces a
published comparison that is measuring the harness.
"""

from __future__ import annotations

from augury.prompts import raw

ANALYST = raw("analyst")
BASELINE = raw("baseline")


# Every rule the falsifiability gate enforces, in the words the prompts use.
# A rule reworded in one arm and not the other is the asymmetry this file
# exists to catch, so the list is checked against both -- and checked for
# being present at all, since a phrase with a typo in it is in neither arm and
# would otherwise pass twice over.
VALIDATOR_RULES = (
    "greater than `value`",  # which bound is which
    "at least 1",  # the floor a unit can measure
    "hundredfold",  # the widest honest band
    "8 to 27",  # when a range is honest rather than evasive
)


def test_every_validator_rule_is_stated_somewhere() -> None:
    """Guards the test below: a rule nobody states passes it vacuously."""
    for rule in VALIDATOR_RULES:
        assert rule in ANALYST, f"nothing states this rule any more: {rule}"


def test_both_arms_learn_what_the_validator_rejects() -> None:
    """The analyst was given the answer key to the falsifiability gate.

    A prediction the validator rejects is recorded as dropped, which lands in
    the falsifiable-precision denominator. Telling one arm the rules and not
    the other moves that metric directly.
    """
    for rule in VALIDATOR_RULES:
        assert rule in BASELINE, f"the baseline is not told: {rule}"


def test_both_arms_learn_when_a_range_is_honest() -> None:
    # This one was missing from the analyst, not the baseline.
    for text in (ANALYST, BASELINE):
        assert "8 to 27" in text


def test_neither_arm_is_told_to_omit_a_required_field() -> None:
    """`DraftFinding.prediction` is required-and-nullable, never absent.

    The baseline was told to "omit entirely", which a strict provider rejects,
    costing retries and -- for a single-call arm -- sometimes the whole run.
    """
    for text in (ANALYST, BASELINE):
        assert "Omit entirely" not in text
        assert "`null`" in text


def test_both_arms_are_told_what_a_symbol_is() -> None:
    """`symbol` is the seeded-recall matching key and the locator's input."""
    for text in (ANALYST, BASELINE):
        assert "function, class or configuration key" in text


def test_both_arms_are_told_the_unit_vocabulary() -> None:
    for text in (ANALYST, BASELINE):
        for unit in ("`ms`", "`queries`", "`rps`"):
            assert unit in text, unit


def test_both_arms_are_told_deployment_configuration_sets_the_conditions() -> None:
    for text in (ANALYST, BASELINE):
        assert "wrong relative to a worker count" in text


def test_every_prediction_subfield_is_described_in_both_arms() -> None:
    for field in ("metric", "comparator", "value", "upper", "unit", "condition"):
        for name, text in (("analyst", ANALYST), ("baseline", BASELINE)):
            assert f"`{field}`" in text, f"{name} does not describe {field}"
