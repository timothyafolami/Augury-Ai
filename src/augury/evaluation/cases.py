"""A case is a repository plus the defects we put in it.

Because the defects are seeded, "did the reviewer find them" has an objective
answer no reviewer can talk its way around. That makes Seeded Defect Recall the
one metric here that cannot be gamed by saying less: saying less can only lower
it.

A case holds several defects rather than one, because a realistic repository
does, and because a fraction distinguishes a reviewer that found two of five
from one that found four. A coin flip does not.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from augury.core.findings import Report

CASES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "eval" / "cases"


class Defect(BaseModel):
    """One thing we broke on purpose, and how to tell whether it was found."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    lab_topic: str = Field(min_length=1, description="The practice-lab topic that defines it")
    defect: str = Field(min_length=1, description="What was seeded, in one sentence")
    locations: tuple[str, ...] = Field(min_length=1)
    symbols: tuple[str, ...] = Field(min_length=1, description="Names that identify it")
    verification: str = Field(min_length=1, description="load, differential or probe")
    expected_metric: str = ""
    notes: str = ""

    def found_in(self, report: Report) -> bool:
        """Whether any finding names this defect, in one of its files.

        A finding elsewhere is not this defect, however real it is; counting it
        would make recall reward volume. Within the right file the identifying
        name may appear in the symbol or in the prose, because reviewers name a
        construct either way and penalising that measures formatting rather
        than detection.

        The name must appear as a whole word. Substring matching turned recall
        into a lottery: `except` matched "an exception type is not declared",
        `balance` matched "should load-balance across replicas", and five
        findings describing nothing seeded scored a perfect 1.000.
        """
        return any(
            finding.path in self.locations
            and any(
                _mentions(symbol, f"{finding.symbol} {finding.mechanism}")
                for symbol in self.symbols
            )
            for finding in report.findings
        )


class Case(BaseModel):
    """One repository and everything we seeded in it."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    repo_description: str = ""
    defects: tuple[Defect, ...] = Field(min_length=1)
    notes: str = ""
    experiment_conditions_by_metric: dict[str, str] = Field(
        default_factory=dict,
        alias="experiment_conditions",
        description="What scenario each experiment runs, published to every arm",
    )
    repo: Path = Path()

    def experiment_conditions(self) -> dict[str, str]:
        """The scenario each of this case's experiments runs.

        Published to both arms. A reviewer cannot guess a harness's
        parameters, and a prediction about a scenario that was never run is
        scored on something other than its own correctness: on case C01 every
        tested prediction from both arms was a correct diagnosis of a different
        load than the one measured.

        This reveals which metrics a case can measure. It does not reveal where
        the defects are, what the numbers should be, or whether anything is
        wrong at all.
        """
        return dict(self.experiment_conditions_by_metric)

    def found_by(self, report: Report) -> tuple[str, ...]:
        """The ids of the seeded defects this report found, each counted once."""
        return tuple(defect.id for defect in self.defects if defect.found_in(report))

    def recall(self, report: Report) -> float:
        """The share of seeded defects found. Zero is a result, not an absence."""
        return len(self.found_by(report)) / len(self.defects)


def load_cases(root: Path | None = None) -> list[Case]:
    """Every case under `root`, sorted by id."""
    directory = root or CASES_ROOT
    return sorted(
        (
            Case.model_validate(
                json.loads(manifest.read_text(encoding="utf-8"))
                | {"repo": manifest.parent / "repo"}
            )
            for manifest in directory.glob("*/case.json")
        ),
        key=lambda case: case.id,
    )


@lru_cache(maxsize=512)
def _pattern(symbol: str) -> re.Pattern[str]:
    """A whole-word match, tolerating a trailing `()` and a dotted prefix.

    Word boundaries rather than substrings, because `except` inside
    `exception` is not a mention of the handler. Underscores are part of a
    word in Python's own sense, so `pool_size` matches as written.
    """
    return re.compile(rf"(?<![\w-]){re.escape(symbol)}(?![\w-])", re.IGNORECASE)


def _mentions(symbol: str, text: str) -> bool:
    return _pattern(symbol).search(text) is not None
