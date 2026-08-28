"""The vocabulary every agent in the mesh speaks.

The central type is `Prediction`. Analysts produce prose; the Refiner turns
prose into a Prediction or drops it. A Prediction is the only thing the Prover
knows how to test, which is what keeps unfalsifiable output out of the report.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Comparator(StrEnum):
    """How a measurement is compared against the predicted value."""

    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    BETWEEN = "between"


class Outcome(StrEnum):
    """The verdict vocabulary from PREDICTIONS.md.

    BROKEN is not a soft Miss. It means the experiment did not run, so the
    prediction was never tested and must not be scored either way.
    """

    HIT = "hit"
    MISS = "miss"
    BROKEN = "broken"


class Prediction(BaseModel):
    """A claim about production behaviour that a measurement can refute.

    Every field is load-bearing: without a unit and a condition, a claim is
    an opinion, and the lab's rule is that "slower" is not a prediction.

    Frozen, because PREDICTIONS.md forbids editing a prediction once output has
    been seen. The type enforces the rule rather than trusting the operator.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1, description="What is measured, e.g. http_req_duration_p99")
    comparator: Comparator
    value: float = Field(
        allow_inf_nan=False,
        description="Threshold, or the lower bound when comparator is BETWEEN",
    )
    upper: float | None = Field(
        default=None, allow_inf_nan=False, description="Upper bound, BETWEEN only"
    )
    unit: str = Field(min_length=1, description="Dimension of the measurement, e.g. ms, queries, x")
    condition: str = Field(min_length=1, description="The circumstance under which it holds")

    @model_validator(mode="after")
    def _range_must_be_a_real_band(self) -> Prediction:
        if self.comparator is not Comparator.BETWEEN:
            return self
        if self.upper is None:
            raise ValueError("comparator BETWEEN requires an upper bound")
        if self.upper <= self.value:
            raise ValueError("upper bound must exceed the lower bound, or nothing can Hit")
        return self

    def score(self, measured: float | None) -> Outcome:
        """Resolve this prediction against a measurement.

        A measurement that is missing or non-finite means the experiment
        failed to produce a number, which is BROKEN rather than a wrong answer.
        """
        if measured is None or not math.isfinite(measured):
            return Outcome.BROKEN

        match self.comparator:
            case Comparator.AT_LEAST:
                hit = measured >= self.value
            case Comparator.AT_MOST:
                hit = measured <= self.value
            case Comparator.BETWEEN:
                assert self.upper is not None  # guaranteed by the validator
                hit = self.value <= measured <= self.upper
            case unreachable:
                assert_never(unreachable)

        return Outcome.HIT if hit else Outcome.MISS
