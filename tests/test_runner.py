"""Driving one arm over the case set.

Every arm sees identical cases and is scored by identical code. That is the
only thing that makes two rows in the results table comparable, so it is
enforced here rather than promised in prose.

These tests build their own fixture case rather than using the shipped ones:
adding a real case should never break the runner's tests, and a test that
depends on the current case set is measuring the case set.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from augury.core.adapters.base import Usage
from augury.core.scoring import aggregate
from augury.evaluation.cases import Case, load_cases
from augury.evaluation.runner import run_arm


class ScriptedModel:
    model_id = "stub-1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0
        self._usage = Usage()

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        self.calls += 1
        self._usage = self._usage + Usage(input_tokens=10, output_tokens=5, usd=0.002)
        return schema.model_validate_json(json.dumps(self.payload))

    @property
    def usage(self) -> Usage:
        return self._usage

    async def call(self, *, prompt: str, schema: type[BaseModel]):  # type: ignore[no-untyped-def]
        from augury.core.adapters.base import Completion

        before = self.usage
        result = await self.structured(prompt=prompt, schema=schema)
        return Completion(result=result, usage=self.usage - before, retries=0)


FINDS_THE_DEFECT: dict[str, Any] = {
    "findings": [
        {
            "path": "app/db.py",
            "line": 9,
            "layer": "network",
            "symbol": "engine",
            "mechanism": "pool_size is 5 against 8 uvicorn workers",
            "severity": "high",
            "remediation": "raise pool_size to 20",
            "arithmetic": "8 workers, 40ms service time",
            "prediction": {
                "metric": "http_req_duration_p99",
                "comparator": "at_least",
                "value": 1000.0,
                "upper": None,
                "unit": "ms",
                "condition": "rate=250rps",
            },
        }
    ]
}


def fixture_cases() -> list[Case]:
    """One case seeding one defect, built here so the shipped set can grow."""
    root = Path(__file__).parent / "fixtures" / "runner-case"
    return load_cases(root)


FINDS_SOMETHING_ELSE: dict[str, Any] = {
    "findings": [
        {
            "path": "app/main.py",
            "line": 20,
            "layer": "craft",
            "symbol": "health",
            "mechanism": "the health endpoint could be documented better",
            "severity": "low",
            "remediation": "add a docstring",
            "arithmetic": "",
            "prediction": None,
        }
    ]
}


async def test_scores_every_case_and_labels_the_arm(tmp_path: Path) -> None:
    model = ScriptedModel(FINDS_THE_DEFECT)

    scores = await run_arm("baseline", model, fixture_cases())

    assert scores
    assert {s.arm for s in scores} == {"baseline"}
    assert {s.case for s in scores} == {case.id for case in fixture_cases()}


async def test_records_whether_the_seeded_defect_was_found() -> None:
    found = await run_arm("baseline", ScriptedModel(FINDS_THE_DEFECT), fixture_cases())
    missed = await run_arm("baseline", ScriptedModel(FINDS_SOMETHING_ELSE), fixture_cases())

    assert all(s.found == s.seeded for s in found)
    assert all(s.found == 0 for s in missed)


async def test_detection_rate_survives_aggregation() -> None:
    """It is the one metric a reviewer cannot improve by saying less."""
    scores = await run_arm("baseline", ScriptedModel(FINDS_THE_DEFECT), fixture_cases())

    assert aggregate(scores).detection_rate == 1.0


async def test_a_case_that_raises_is_recorded_rather_than_ending_the_sweep() -> None:
    """One provider hiccup must not cost the whole run, and the failure must
    not be silently absent from the denominator."""

    class Failing(ScriptedModel):
        async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
            raise RuntimeError("provider said no")

    scores = await run_arm("baseline", Failing({}), fixture_cases())

    assert all(s.failed for s in scores)
    assert all(s.total_findings == 0 for s in scores)


async def test_the_seed_is_carried_onto_every_score() -> None:
    scores = await run_arm("baseline", ScriptedModel(FINDS_THE_DEFECT), fixture_cases(), seed=7)

    assert {s.seed for s in scores} == {7}


@pytest.mark.parametrize("arm", ["baseline", "augury"])
async def test_the_arm_name_is_recorded_verbatim(arm: str) -> None:
    scores = await run_arm(arm, ScriptedModel(FINDS_THE_DEFECT), fixture_cases())

    assert aggregate(scores).arm == arm


# -- proving ---------------------------------------------------------------


PREDICTS_QUERY_COUNT: dict[str, Any] = {
    "findings": [
        {
            "path": "app/db.py",
            "line": 3,
            "layer": "data",
            "symbol": "engine",
            "mechanism": "a query per order",
            "severity": "high",
            "remediation": "eager load",
            "arithmetic": "one per row plus the list",
            "prediction": {
                "metric": "queries_per_request",
                "comparator": "at_most",
                "value": 2.0,
                "upper": None,
                "unit": "queries",
                "condition": "50 orders",
            },
        }
    ]
}


async def test_predictions_are_tested_when_the_case_ships_an_experiment() -> None:
    """Without this the reviewer's numbers are never checked, and hit rate is
    the metric that decides whether they were worth making."""
    cases = load_cases()
    provable = [c for c in cases if (c.repo.parent / "experiments").is_dir()]
    if not provable:
        pytest.skip("no case ships an experiment yet")

    scores = await run_arm("baseline", ScriptedModel(PREDICTS_QUERY_COUNT), provable, prove=True)

    assert any(s.tested for s in scores), "a shipped experiment was never run"


async def test_proving_is_off_by_default() -> None:
    """Experiments cost real time. A run that did not ask for them must not
    silently pay for them."""
    scores = await run_arm("baseline", ScriptedModel(PREDICTS_QUERY_COUNT), fixture_cases())

    assert all(s.tested == 0 for s in scores)
