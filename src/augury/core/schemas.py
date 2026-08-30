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

# A measurement larger than this is not something an experiment produces; a
# threshold above it excludes nothing. Deliberately generous: a p99 of a
# billion milliseconds is eleven days.
VACUOUS_CEILING = 1e9

# A range is honest when it is wide because the mechanism is uncertain. Beyond
# two orders of magnitude it stops being a claim about anything.
WIDEST_HONEST_BAND = 100.0


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


# The span a measurement in each unit can plausibly land in. A threshold at or
# outside its own unit's range excludes nothing that can happen, which is the
# definition of vacuous -- and pinning the guard to zero instead let the
# perfect-score attack back in one epsilon above it: `p99 >= 0.000001ms` hits
# every measurement ever taken and passed the gate.
#
# Deliberately generous. The purpose is to catch a claim that cannot lose, not
# to referee whether a number is likely.
REALISABLE = {
    "ms": (1.0, 3_600_000.0),
    "s": (0.001, 3_600.0),
    "seconds": (0.001, 3_600.0),
    "queries": (1.0, 1e9),
    "query": (1.0, 1e9),
    "requests": (1.0, 1e12),
    "connections": (1.0, 1e6),
    "bytes": (1.0, 1e15),
    "mb": (0.001, 1e9),
    "x": (1.0, 1e6),
    "%": (0.01, 100.0),
    "percent": (0.01, 100.0),
    "rps": (0.01, 1e9),
}

# For a unit nobody anticipated. Excludes only what the old guard did, so an
# unfamiliar unit is never rejected for being unfamiliar.
UNKNOWN_UNIT = (0.0, VACUOUS_CEILING)


def realisable_range(unit: str) -> tuple[float, float]:
    """The smallest and largest a measurement in this unit plausibly is.

    A count cannot be fractional and a latency is not measured below the
    millisecond, so "at least one query" and "under a millisecond" exclude
    nothing that occurs -- while reading as real thresholds.
    """
    return REALISABLE.get(unit.strip().lower(), UNKNOWN_UNIT)


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
    def _must_be_refutable(self) -> Prediction:
        """Reject claims that no realisable measurement could contradict.

        The first version of this type rejected the never-hit shape (an
        inverted band) and accepted the always-hit shape. That asymmetry was
        fatal: a reviewer emitting only `p99 >= 0ms` scored a perfect hit rate
        while saying nothing, and beat an honest reviewer on both headline
        metrics. A prediction has to exclude some part of the outcome space or
        it is not a prediction.
        """
        floor, ceiling = realisable_range(self.unit)
        if self.comparator is Comparator.AT_LEAST and self.value <= floor:
            raise ValueError(
                f"vacuous: essentially every measurement in {self.unit} is at least "
                f"{floor:g}, so this threshold excludes nothing"
            )
        if self.comparator is Comparator.AT_MOST and self.value >= ceiling:
            raise ValueError(
                f"vacuous: no realisable measurement in {self.unit} exceeds "
                f"{ceiling:g}, so this threshold excludes nothing"
            )
        if self.comparator is Comparator.BETWEEN and self.upper is not None:
            if self.value <= 0:
                raise ValueError("vacuous: a band starting at or below zero excludes nothing")
            if self.upper / self.value > WIDEST_HONEST_BAND:
                raise ValueError(
                    f"vacuous: a band spanning more than {WIDEST_HONEST_BAND:g}x "
                    "admits almost every outcome"
                )
        return self

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
