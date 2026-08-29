"""A prediction is about a scenario. The experiment has to run that one.

Both arms scored a hit rate of 0.000 on case C01 across seventeen tested
predictions -- not because they were wrong, but because they were right about
a different scenario:

    claim    queries_per_request at least 101, reporting 100 shipments
    measured 41, because the experiment reports 40

The diagnosis was correct and the verdict was meaningless. A reviewer cannot
guess a harness's parameters, and scoring it as though it should have is the
same mistake as expecting it to guess a metric name.

So each case publishes the conditions its experiments run under, to both arms
identically. This does reveal which metrics a case can measure. It does not
reveal where the defects are, what the numbers should be, or whether anything
is wrong -- and the alternative is a number that means nothing.
"""

import pytest

from augury.evaluation.cases import load_cases
from augury.prompts import raw


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.id)
def test_every_metric_a_case_can_measure_declares_its_conditions(case) -> None:  # type: ignore[no-untyped-def]
    directory = case.repo.parent / "experiments"
    if not directory.is_dir():
        pytest.skip(f"{case.id} ships no experiments")

    conditions = case.experiment_conditions()
    for script in directory.glob("*.py"):
        assert script.stem in conditions, (
            f"{case.id} runs {script.stem} without saying under what conditions, "
            "so a prediction about it can only be right by luck"
        )
        assert len(conditions[script.stem]) > 10, f"{case.id}/{script.stem} says too little"


@pytest.mark.parametrize("prompt", ["analyst", "baseline"])
def test_both_arms_are_told_the_conditions(prompt: str) -> None:
    """Telling one arm the scenario and not the other would decide the hit
    rate before either ran."""
    assert "{experiments}" in raw(prompt)


def test_the_conditions_do_not_say_what_is_wrong() -> None:
    """They describe the scenario, not the defect or the expected number."""
    leaks = ("defect", "seeded", "bug", "should be", "incorrect", "wrong")

    for case in load_cases():
        for metric, condition in case.experiment_conditions().items():
            lowered = condition.lower()
            for leak in leaks:
                assert leak not in lowered, f"{case.id}/{metric} gives away the answer"


def test_a_case_with_no_experiments_offers_no_conditions() -> None:
    easy = next(c for c in load_cases() if c.id == "A04")

    assert easy.experiment_conditions() == {}
