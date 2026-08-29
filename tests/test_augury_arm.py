"""The pipeline arm: schedule, triage, specialists, refine.

Its claim over the baseline is not that it is a bigger model. It is that it
chooses what to read, routes each file only to specialists that can say
something about it, and refuses to publish a claim it cannot make testable.
Each of those is asserted here, because each is what the extra cost buys.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from augury.agents.augury import AuguryReviewer
from augury.core.adapters.base import Usage
from augury.core.cartography import Cartographer
from augury.core.scheduling import Budget


class RoutingModel:
    """Answers by schema, and records every prompt it was given."""

    model_id = "stub-1"

    def __init__(self, **by_schema: dict[str, Any]) -> None:
        self.by_schema = by_schema
        self.prompts: list[tuple[str, str]] = []
        self._usage = Usage()

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        self.prompts.append((schema.__name__, prompt))
        self._usage = self._usage + Usage(input_tokens=10, output_tokens=5, usd=0.001)
        return schema.model_validate_json(json.dumps(self.by_schema[schema.__name__]))

    @property
    def usage(self) -> Usage:
        return self._usage

    def prompts_for(self, schema: str) -> list[str]:
        return [prompt for name, prompt in self.prompts if name == schema]


ROUTES_TO_DATA: dict[str, Any] = {"specialists": ["data"], "reasoning": "an ORM session"}

ONE_FINDING: dict[str, Any] = {
    "findings": [
        {
            "path": "app/db.py",
            "line": 9,
            "layer": "data",
            "symbol": "engine",
            "mechanism": "pool_size is 5 against 8 workers",
            "severity": "high",
            "remediation": "raise pool_size",
            "arithmetic": "8 workers at 40ms",
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


def model(**overrides: dict[str, Any]) -> RoutingModel:
    return RoutingModel(
        **{"TriageDecision": ROUTES_TO_DATA, "DraftReport": ONE_FINDING} | overrides
    )


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "db.py").write_text("import sqlalchemy\n\npool_size = 5\n")
    (tmp_path / "app" / "notes.py").write_text("VERSION = '1.0'\n")
    return tmp_path


async def test_produces_findings_from_the_routed_specialist(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    stub = model()

    report = await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    assert len(report.findings) == 1
    assert report.findings[0].is_falsifiable


async def test_a_module_with_no_signal_is_never_sent_to_a_model(tmp_path: Path) -> None:
    """The saving is the point. Reading a file no specialist can speak about
    is spend with a known-zero expected return."""
    root = make_repo(tmp_path)
    stub = model()

    await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    assert not any("notes.py" in prompt for prompt in stub.prompts_for("TriageDecision"))


async def test_only_the_specialists_triage_chose_are_invoked(tmp_path: Path) -> None:
    """Fanning out to all eight would cost eight times as much and produce
    seven confident opinions from reviewers with nothing to look at."""
    root = make_repo(tmp_path)
    stub = model()

    await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    analyst_prompts = stub.prompts_for("DraftReport")
    assert len(analyst_prompts) == 1
    assert "data" in analyst_prompts[0].lower()


async def test_the_specialist_brief_reaches_the_prompt(tmp_path: Path) -> None:
    """The specialist's authority is the lab layer it was written from. If the
    brief is not in the prompt, the specialist is just a label."""
    root = make_repo(tmp_path)
    stub = model()

    await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    assert "isolation" in stub.prompts_for("DraftReport")[0].lower()


async def test_triage_choosing_nobody_costs_nothing_further(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    stub = model(TriageDecision={"specialists": [], "reasoning": "nothing here"})

    report = await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    assert stub.prompts_for("DraftReport") == []
    assert report.findings == ()


async def test_the_budget_stops_the_review(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    stub = model()

    report = await AuguryReviewer(stub, budget=Budget(usd=0.0001, calls_per_module=3)).review(
        Cartographer(root).map(), root
    )

    assert stub.prompts == []
    assert report.coverage is not None
    assert report.coverage.skipped


async def test_coverage_reports_what_was_read_and_what_was_not(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    report = await AuguryReviewer(model()).review(Cartographer(root).map(), root)

    assert report.coverage is not None
    assert report.coverage.analysed == ["app/db.py"]
    assert "app/notes.py" in report.coverage.skipped


async def test_cost_is_the_sum_of_every_call(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    stub = model()

    report = await AuguryReviewer(stub).review(Cartographer(root).map(), root)

    assert report.usd == stub.usage.usd
    assert report.usd > 0
