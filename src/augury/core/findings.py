"""What a review produces.

A `Finding` is what a specialist saw. A `Prediction` attached to it is what the
Refiner was able to make testable, and a `verdict` is what the Prover measured.
The three stages are separate fields rather than one blob, so a report can
always say which stage a claim reached.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from augury.core.scheduling import Coverage
from augury.core.schemas import Outcome, Prediction


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    """One thing a specialist saw, and how far it got toward being proved."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    line: int = Field(ge=0)
    layer: str = Field(min_length=1, description="The specialist that raised it")
    symbol: str = Field(min_length=1, description="Function, class or config key")
    mechanism: str = Field(min_length=1, description="Why this fails, in terms of the corpus")
    severity: Severity
    remediation: str = Field(min_length=1, description="The change, stated as a change")

    prediction: Prediction | None = Field(
        default=None, description="Set by the Refiner when the claim was made testable"
    )
    arithmetic: str = Field(default="", description="How the threshold was derived")
    verdict: Outcome | None = Field(
        default=None, description="Set by the Prover once the experiment has run"
    )
    measured: float | None = Field(default=None, description="What the experiment observed")

    @model_validator(mode="after")
    def _a_verdict_requires_a_prediction(self) -> Finding:
        if self.verdict is not None and self.prediction is None:
            raise ValueError("a verdict requires a prediction: nothing else could be tested")
        return self

    @property
    def is_falsifiable(self) -> bool:
        return self.prediction is not None

    @property
    def was_tested(self) -> bool:
        """Broken means the experiment did not run, so nothing was tested."""
        return self.verdict in (Outcome.HIT, Outcome.MISS)


class Report(BaseModel):
    """Everything one review produced, including what it could not use."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)
    dropped: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Findings the Refiner could not make falsifiable, with the reason",
    )
    coverage: Coverage | None = Field(default=None, description="What was read and what was not")
    model_id: str = ""
    usd: float = 0.0
    seconds: float = 0.0
