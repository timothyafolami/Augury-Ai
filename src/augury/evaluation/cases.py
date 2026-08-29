"""A case is a repository plus the defect we put in it.

Because the defect is seeded, "did the reviewer find it" has an objective
answer that no reviewer can talk its way around. That makes Seeded Defect
Recall the one metric here that cannot be gamed by saying less: saying less can
only lower it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from augury.core.findings import Report

CASES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "eval" / "cases"


class Case(BaseModel):
    """One seeded defect, and how to tell whether it was found."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    lab_topic: str = Field(min_length=1, description="The practice-lab topic that defines it")
    defect: str = Field(min_length=1, description="What was seeded, in one sentence")
    locations: tuple[str, ...] = Field(min_length=1)
    symbols: tuple[str, ...] = Field(min_length=1, description="Names that identify the defect")
    verification: str = Field(min_length=1, description="load, differential or probe")
    expected_metric: str = ""
    notes: str = ""
    repo: Path = Path()

    def detected_by(self, report: Report) -> bool:
        """Whether any finding names this defect, in the right file.

        A finding elsewhere is not this defect, however real it is; counting it
        would make recall reward volume. Within the right file, the identifying
        name may appear in the symbol or in the prose, because reviewers name a
        construct either way and penalising that measures formatting rather
        than detection.
        """
        return any(
            finding.path in self.locations
            and any(
                symbol.lower() in f"{finding.symbol} {finding.mechanism}".lower()
                for symbol in self.symbols
            )
            for finding in report.findings
        )


def load_cases(root: Path | None = None) -> list[Case]:
    """Every case under `root`, sorted by id."""
    directory = root or CASES_ROOT
    cases = [
        Case.model_validate(
            json.loads(manifest.read_text(encoding="utf-8"))
            | {"repo": manifest.parent / "repo"}
        )
        for manifest in sorted(directory.glob("*/case.json"))
    ]
    return sorted(cases, key=lambda case: case.id)
