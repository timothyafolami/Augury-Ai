"""Running the experiment that settles a prediction.

The integrity property here is that experiments are code shipped with the case,
which a judge can read and run, and never something the reviewer invents. A
reviewer that supplied its own measurement would be grading its own homework,
which is the failure the whole measurement layer is built to prevent.

A prediction that cannot be tested is Broken, never a Miss. Broken means the
harness did not answer; scoring it as a wrong answer would punish the reviewer
for our infrastructure.
"""

import json
from pathlib import Path

import pytest

from augury.core.schemas import Comparator, Outcome, Prediction
from augury.evaluation.cases import Case, load_cases
from augury.evaluation.prover import Prover


def prediction(metric: str = "queries_per_request", value: float = 2.0) -> Prediction:
    return Prediction(
        metric=metric,
        comparator=Comparator.AT_MOST,
        value=value,
        unit="queries",
        condition="50 orders",
    )


def case_with_experiment(tmp_path: Path, body: str, metric: str = "queries_per_request") -> Case:
    directory = tmp_path / "T01"
    (directory / "repo").mkdir(parents=True)
    (directory / "experiments").mkdir(parents=True)
    (directory / "experiments" / f"{metric}.py").write_text(body)
    (directory / "case.json").write_text(
        json.dumps(
            {
                "id": "T01",
                "name": "t",
                "defects": [
                    {
                        "id": "T01-1",
                        "lab_topic": "03-data/06",
                        "defect": "n+1",
                        "locations": ["a.py"],
                        "symbols": ["s"],
                        "verification": "differential",
                    }
                ],
            }
        )
    )
    return load_cases(tmp_path)[0]


async def test_runs_the_experiment_and_returns_what_it_measured(tmp_path: Path) -> None:
    case = case_with_experiment(tmp_path, "print(51)\n")

    measurement = await Prover(case).prove(prediction())

    assert measurement.value == 51.0


async def test_the_verdict_follows_from_the_measurement(tmp_path: Path) -> None:
    """51 queries against a claim of at most 2 is a Miss, and the prediction
    says so; nothing else gets an opinion."""
    case = case_with_experiment(tmp_path, "print(51)\n")

    measurement = await Prover(case).prove(prediction())

    assert prediction().score(measurement.value) is Outcome.MISS


async def test_a_metric_with_no_experiment_is_broken_not_a_miss(tmp_path: Path) -> None:
    case = case_with_experiment(tmp_path, "print(1)\n")

    measurement = await Prover(case).prove(prediction(metric="worker_saturation"))

    assert measurement.value is None
    assert "no experiment" in measurement.detail


async def test_an_experiment_that_crashes_is_broken(tmp_path: Path) -> None:
    """The reviewer's claim was never tested, so it must not be scored."""
    case = case_with_experiment(tmp_path, "raise SystemExit(3)\n")

    measurement = await Prover(case).prove(prediction())

    assert measurement.value is None


async def test_an_experiment_that_prints_nothing_numeric_is_broken(tmp_path: Path) -> None:
    case = case_with_experiment(tmp_path, "print('it worked, probably')\n")

    measurement = await Prover(case).prove(prediction())

    assert measurement.value is None
    assert "number" in measurement.detail


async def test_an_experiment_that_hangs_is_stopped_and_broken(tmp_path: Path) -> None:
    case = case_with_experiment(tmp_path, "import time; time.sleep(30)\n")

    measurement = await Prover(case, timeout=1.0).prove(prediction())

    assert measurement.value is None
    assert "timed out" in measurement.detail


async def test_the_experiment_is_identified_so_one_run_counts_once(tmp_path: Path) -> None:
    """Twenty findings sharing a mechanism share an experiment, and the score
    counts experiments rather than findings."""
    case = case_with_experiment(tmp_path, "print(7)\n")

    measurement = await Prover(case).prove(prediction())

    assert measurement.experiment == "T01/queries_per_request"


async def test_the_last_number_printed_is_the_measurement(tmp_path: Path) -> None:
    """Experiments log while they work. The result is what they end with."""
    case = case_with_experiment(tmp_path, "print('setting up')\nprint('rows: 1000')\nprint(4)\n")

    assert (await Prover(case).prove(prediction())).value == 4.0


@pytest.mark.parametrize("shipped", load_cases())
def test_every_shipped_experiment_names_a_metric_some_defect_expects(shipped: Case) -> None:
    """An experiment nothing predicts is dead weight, and a defect whose
    expected metric has no experiment can never be proved."""
    directory = shipped.repo.parent / "experiments"
    if not directory.is_dir():
        pytest.skip(f"{shipped.id} ships no experiments yet")

    expected = {d.expected_metric for d in shipped.defects if d.expected_metric}
    for script in directory.glob("*.py"):
        assert script.stem in expected, f"{shipped.id}: nothing predicts {script.stem}"
