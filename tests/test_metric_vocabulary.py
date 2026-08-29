"""A prediction can only be tested if it names something the harness measures.

The vocabulary exists because both arms independently invented metric names,
and every prediction they made was Broken for want of a shared word.
"""

import pytest

from augury.core.metrics import METRICS, vocabulary
from augury.evaluation.cases import load_cases
from augury.prompts import raw


@pytest.mark.parametrize("prompt", ["analyst", "baseline"])
def test_both_arms_are_given_the_same_vocabulary(prompt: str) -> None:
    """Publishing it to one arm and not the other would decide the comparison
    before either ran."""
    text = raw(prompt)

    assert "{metrics}" in text, f"{prompt}.md never receives the metric vocabulary"


def test_the_vocabulary_is_the_same_for_every_case() -> None:
    """A per-case list would tell the reviewer which defect to look for."""
    rendered = vocabulary()

    for case in load_cases():
        assert rendered == vocabulary(), f"{case.id} would see a different vocabulary"


def test_every_shipped_experiment_measures_a_metric_in_the_vocabulary() -> None:
    """An experiment named outside the vocabulary can never be reached, because
    no valid prediction can name it."""
    for case in load_cases():
        directory = case.repo.parent / "experiments"
        if not directory.is_dir():
            continue
        for script in directory.glob("*.py"):
            assert script.stem in METRICS, (
                f"{case.id} ships {script.stem}.py, which no prediction may name"
            )


def test_every_expected_metric_a_case_declares_is_in_the_vocabulary() -> None:
    for case in load_cases():
        for defect in case.defects:
            if defect.expected_metric:
                assert defect.expected_metric in METRICS, (
                    f"{case.id}/{defect.id} expects {defect.expected_metric}, "
                    "which no prediction may name"
                )


def test_the_vocabulary_reads_as_instructions_not_as_a_bare_list() -> None:
    """Each entry says what the number means, so a reviewer picks the right
    one rather than the closest-looking name."""
    for line in vocabulary().splitlines():
        assert ": " in line, f"{line} does not say what it measures"
