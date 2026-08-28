"""What a review produces.

A `Finding` is what a specialist saw. A `Prediction` attached to it is what the
Refiner made testable. A `Measurement` is what the Prover observed. The verdict
is not stored: it is derived from the prediction and the measurement, so no
component can assert a grade it did not earn.

Findings and reports are frozen for the same reason. `Prediction` was already
immutable, but the reference to it was not, so a prediction could be swapped
after the experiment ran and the report would still validate.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from augury.core.scheduling import Coverage
from augury.core.schemas import Outcome, Prediction


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Measurement(BaseModel):
    """What an experiment observed.

    A `value` of None means the experiment ran and produced no usable number,
    which is Broken. No `Measurement` at all means it never ran, which is not
    a verdict of any kind.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float | None
    experiment: str = Field(
        default="", description="Identifies the run, so one run answering many findings counts once"
    )
    detail: str = ""


class Finding(BaseModel):
    """One thing a specialist saw, and how far it got toward being proved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=4096)
    line: int = Field(ge=0)
    layer: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=512)
    mechanism: str = Field(min_length=1, max_length=4096)
    severity: Severity
    remediation: str = Field(min_length=1, max_length=4096)

    prediction: Prediction | None = None
    arithmetic: str = Field(default="", max_length=4096)
    measurement: Measurement | None = None

    @model_validator(mode="after")
    def _a_measurement_requires_a_prediction(self) -> Finding:
        if self.measurement is not None and self.prediction is None:
            raise ValueError("a measurement requires a prediction: nothing else was being tested")
        return self

    @property
    def is_falsifiable(self) -> bool:
        return self.prediction is not None

    @property
    def verdict(self) -> Outcome | None:
        """Derived, never asserted. None means the experiment did not run."""
        if self.prediction is None or self.measurement is None:
            return None
        return self.prediction.score(self.measurement.value)

    @property
    def was_tested(self) -> bool:
        """Broken means the experiment produced no number, so nothing was tested."""
        return self.verdict in (Outcome.HIT, Outcome.MISS)


class Dropped(BaseModel):
    """A finding the Refiner could not make falsifiable, and why.

    Schema'd rather than a loose dict, because this list is the counterweight
    to the precision denominator and an empty dict must not count toward it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=512)
    path: str = Field(min_length=1, max_length=4096)
    reason: str = Field(min_length=1, max_length=2048)


class Report(BaseModel):
    """Everything one review produced, including what it could not use."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[Finding, ...] = ()
    dropped: tuple[Dropped, ...] = ()
    coverage: Coverage | None = None
    model_id: str = ""
    usd: float = 0.0
    seconds: float = 0.0
