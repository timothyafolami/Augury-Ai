"""What `--seeds` actually varies, which is nothing about the input.

Recording a five-seed sweep produced identical results in all five, because
cassettes key on (model, prompt, schema) and every seed sends a byte-identical
prompt. That is the cassette being right and the name being misleading: `seed`
is a label attached to a repeat, not a parameter of the run.

The published seed-to-seed range therefore measures provider nondeterminism at
temperature 0. It is not a sample over anything the harness varied, and it must
not be read as a confidence interval. This test exists so that stays true, or
stops being true loudly.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from augury.core.adapters.base import Completion, Usage
from augury.core.findings import Report
from augury.evaluation.cases import Case, load_cases
from augury.evaluation.runner import run_arm


class _RecordingModel:
    """Satisfies ChatModel and refuses to be called: this path uses a reviewer."""

    model_id = "test-model"

    @property
    def usage(self) -> Usage:  # pragma: no cover - never read on this path
        return Usage()

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        raise AssertionError("the reviewer answers; the model is never called here")

    async def call[T: BaseModel](self, *, prompt: str, schema: type[T]) -> Completion:
        raise AssertionError("the reviewer answers; the model is never called here")


def _case() -> Case:
    """A real case, so this pins the shipped shape rather than a convenient one."""
    return load_cases()[0]


def test_the_seed_reaches_the_score_and_nothing_else() -> None:
    """The reviewer is handed the case and is told nothing about the seed."""
    seen: list[Case] = []

    async def reviewer(case: Case) -> Report:
        seen.append(case)
        return Report(model_id="test-model")

    async def sweep() -> list[int]:
        scores = []
        for seed in (0, 1, 2):
            results = await run_arm(
                "augury", _RecordingModel(), [_case()], seed=seed, reviewer=reviewer
            )
            scores.append(results[0].seed)
        return scores

    seeds = asyncio.run(sweep())

    # The label is carried through to the score...
    assert seeds == [0, 1, 2]
    # ...and every run received an identical case. Nothing about the input
    # differs, so two seeds differ only in what the provider chose to say.
    assert len({c.model_dump_json() for c in seen}) == 1
    assert len(seen) == 3
