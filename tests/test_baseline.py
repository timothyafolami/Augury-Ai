"""The baseline is what a competent engineer does today.

One well-written prompt, the whole repository in it, no tools, one shot. It is
asked for exactly what the full pipeline is asked for, including a falsifiable
prediction, because a baseline denied the chance to be falsifiable would lose
by construction and the comparison would prove nothing.

It must be a genuinely strong prompt. A weak baseline makes a win meaningless.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from augury.agents.baseline import BaselineReviewer
from augury.core.adapters.base import Usage
from augury.core.cartography import Cartographer


class ScriptedModel:
    """Returns a prepared answer and remembers what it was asked."""

    model_id = "stub-1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.prompts: list[str] = []
        self._usage = Usage()

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        self._usage = self._usage + Usage(input_tokens=100, output_tokens=50, usd=0.001)
        return schema.model_validate_json(json.dumps(self.payload))

    @property
    def usage(self) -> Usage:
        return self._usage


ONE_GOOD_FINDING: dict[str, Any] = {
    "findings": [
        {
            "path": "app/db.py",
            "line": 31,
            "layer": "data",
            "symbol": "get_session",
            "mechanism": "pool_size=5 against 8 workers",
            "severity": "high",
            "remediation": "raise pool_size to 20",
            "arithmetic": "Little's Law at 40ms service time",
            "prediction": {
                "metric": "http_req_duration_p99",
                "comparator": "at_least",
                "value": 1000.0,
                "unit": "ms",
                "condition": "rate=250rps",
            },
        }
    ]
}


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "db.py").write_text("import sqlalchemy\n\npool_size = 5\n")
    return tmp_path


async def test_produces_a_report_from_one_call(tmp_path: Path) -> None:
    """One shot is the definition of this arm. More than one would make it a
    different system and the comparison dishonest."""
    model = ScriptedModel(ONE_GOOD_FINDING)
    root = make_repo(tmp_path)

    report = await BaselineReviewer(model).review(Cartographer(root).map(), root)

    assert len(model.prompts) == 1
    assert len(report.findings) == 1
    assert report.findings[0].is_falsifiable


async def test_the_baseline_is_asked_for_a_falsifiable_prediction(tmp_path: Path) -> None:
    """The comparison is only meaningful if both arms are asked the same
    question."""
    model = ScriptedModel(ONE_GOOD_FINDING)
    root = make_repo(tmp_path)

    await BaselineReviewer(model).review(Cartographer(root).map(), root)

    prompt = model.prompts[0].lower()
    assert "falsifiable" in prompt or "number" in prompt
    assert "unit" in prompt
    assert "condition" in prompt


async def test_the_source_is_in_the_prompt(tmp_path: Path) -> None:
    model = ScriptedModel(ONE_GOOD_FINDING)
    root = make_repo(tmp_path)

    await BaselineReviewer(model).review(Cartographer(root).map(), root)

    assert "pool_size = 5" in model.prompts[0]


async def test_records_what_the_run_cost(tmp_path: Path) -> None:
    model = ScriptedModel(ONE_GOOD_FINDING)
    root = make_repo(tmp_path)

    report = await BaselineReviewer(model).review(Cartographer(root).map(), root)

    assert report.usd == pytest.approx(0.001)
    assert report.model_id == "stub-1"
    assert report.seconds >= 0


async def test_a_repository_too_large_for_one_prompt_is_truncated_and_says_so(
    tmp_path: Path,
) -> None:
    """A single prompt has a context limit; that limit is the whole point of
    this arm. Truncating silently would overstate what the baseline saw."""
    root = tmp_path
    (root / "app").mkdir()
    for index in range(40):
        (root / "app" / f"m{index}.py").write_text("import sqlalchemy\n" + "x = 1\n" * 400)

    model = ScriptedModel({"findings": []})
    report = await BaselineReviewer(model, char_budget=2_000).review(
        Cartographer(root).map(), root
    )

    assert len(model.prompts[0]) < 20_000
    assert report.coverage is not None
    assert report.coverage.skipped, "files left out of the prompt must be reported"


async def test_an_empty_repository_yields_an_empty_report(tmp_path: Path) -> None:
    """And costs nothing, because there is nothing to ask about."""
    model = ScriptedModel({"findings": []})

    report = await BaselineReviewer(model).review(Cartographer(tmp_path).map(), tmp_path)

    assert report.findings == ()
    assert model.prompts == []
    assert report.usd == 0.0
