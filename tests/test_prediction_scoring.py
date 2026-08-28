"""A prediction is only worth making if a measurement can refute it.

These tests pin the scoring rules from PREDICTIONS.md: every prediction
resolves to Hit, Miss, or Broken, and a failed experiment is never a Miss.
"""

import pytest
from pydantic import ValidationError

from augury.core.schemas import Comparator, Outcome, Prediction


def _p99_at_250rps() -> Prediction:
    return Prediction(
        metric="http_req_duration_p99",
        comparator=Comparator.AT_LEAST,
        value=1000.0,
        unit="ms",
        condition="rate=250rps",
    )


def test_at_least_prediction_hits_when_measurement_reaches_threshold() -> None:
    assert _p99_at_250rps().score(measured=1240.0) is Outcome.HIT


def test_at_least_prediction_misses_when_measurement_stays_below() -> None:
    assert _p99_at_250rps().score(measured=400.0) is Outcome.MISS


def test_at_most_prediction_hits_when_measurement_stays_under() -> None:
    prediction = Prediction(
        metric="queries_per_request",
        comparator=Comparator.AT_MOST,
        value=2.0,
        unit="queries",
        condition="orders list, 50 rows",
    )
    assert prediction.score(measured=2.0) is Outcome.HIT


def test_range_prediction_hits_inside_the_band() -> None:
    prediction = Prediction(
        metric="retry_amplification",
        comparator=Comparator.BETWEEN,
        value=8.0,
        upper=27.0,
        unit="x",
        condition="3 hops, 3 retries each",
    )
    assert prediction.score(measured=19.0) is Outcome.HIT


def test_range_prediction_misses_outside_the_band() -> None:
    prediction = Prediction(
        metric="retry_amplification",
        comparator=Comparator.BETWEEN,
        value=8.0,
        upper=27.0,
        unit="x",
        condition="3 hops, 3 retries each",
    )
    assert prediction.score(measured=3.0) is Outcome.MISS


def test_failed_experiment_scores_broken_rather_than_miss() -> None:
    """A Broken experiment proves nothing. Counting it as a Miss would
    silently reward a reviewer whose harness cannot run."""
    assert _p99_at_250rps().score(measured=None) is Outcome.BROKEN


def test_range_prediction_requires_an_upper_bound() -> None:
    with pytest.raises(ValidationError, match="upper"):
        Prediction(
            metric="retry_amplification",
            comparator=Comparator.BETWEEN,
            value=8.0,
            unit="x",
            condition="3 hops",
        )


def test_prediction_rejects_a_vague_unit() -> None:
    """'Slower' is not a prediction; '3-8x slower' is. A unit that carries
    no dimension makes the claim unfalsifiable."""
    with pytest.raises(ValidationError):
        Prediction(
            metric="latency",
            comparator=Comparator.AT_LEAST,
            value=1.0,
            unit="",
            condition="under load",
        )


# -- comparator branches ---------------------------------------------------
# Mutation testing showed the falsifying direction of AT_MOST, the upper half
# of BETWEEN, and every inclusive boundary were unpinned: `hit = True` for
# AT_MOST survived the whole suite.


def test_at_most_prediction_misses_when_measurement_exceeds_the_ceiling() -> None:
    prediction = Prediction(
        metric="queries_per_request",
        comparator=Comparator.AT_MOST,
        value=2.0,
        unit="queries",
        condition="orders list, 50 rows",
    )
    assert prediction.score(measured=51.0) is Outcome.MISS


def test_range_prediction_misses_above_the_upper_bound() -> None:
    """Without this, BETWEEN degrades silently into AT_LEAST and a predicted
    8-27x amplification would score a Hit at a measured 400x."""
    prediction = Prediction(
        metric="retry_amplification",
        comparator=Comparator.BETWEEN,
        value=8.0,
        upper=27.0,
        unit="x",
        condition="3 hops, 3 retries each",
    )
    assert prediction.score(measured=400.0) is Outcome.MISS


@pytest.mark.parametrize(
    ("comparator", "value", "upper", "measured"),
    [
        (Comparator.AT_LEAST, 1000.0, None, 1000.0),
        (Comparator.AT_MOST, 2.0, None, 2.0),
        (Comparator.BETWEEN, 8.0, 27.0, 8.0),
        (Comparator.BETWEEN, 8.0, 27.0, 27.0),
    ],
)
def test_thresholds_are_inclusive(
    comparator: Comparator, value: float, upper: float | None, measured: float
) -> None:
    """Inclusivity at the threshold is where a scoring rule silently flips a
    published Hit into a Miss. It is pinned, not left to the implementation."""
    prediction = Prediction(
        metric="m", comparator=comparator, value=value, upper=upper, unit="ms", condition="c"
    )
    assert prediction.score(measured=measured) is Outcome.HIT


@pytest.mark.parametrize("field", ["metric", "unit", "condition"])
def test_every_field_that_makes_a_claim_falsifiable_is_required(field: str) -> None:
    """A claim without a metric, a unit or a condition is an opinion."""
    fields: dict[str, str] = {"metric": "latency", "unit": "ms", "condition": "under load"}
    fields[field] = ""

    with pytest.raises(ValidationError, match=field):
        Prediction(comparator=Comparator.AT_LEAST, value=1.0, **fields)  # type: ignore[arg-type]


# -- invariants a Refiner could violate ------------------------------------
# The Refiner is a language model. These are the shapes it will eventually
# emit, and each one is an unfalsifiable claim wearing a falsifiable type.


def test_an_inverted_range_is_rejected() -> None:
    """value=27, upper=8 validates cleanly and can never be Hit: an
    unfalsifiable prediction, which is the one thing this type must prevent."""
    with pytest.raises(ValidationError, match="upper"):
        Prediction(
            metric="retry_amplification",
            comparator=Comparator.BETWEEN,
            value=27.0,
            upper=8.0,
            unit="x",
            condition="3 hops",
        )


def test_a_non_finite_measurement_is_broken_not_a_miss() -> None:
    """A p99 over an empty window, a divide-by-zero ratio and a Prometheus gap
    all arrive as NaN. Scoring those as MISS rewards a harness that cannot run,
    which is exactly what BROKEN exists to prevent."""
    assert _p99_at_250rps().score(measured=float("nan")) is Outcome.BROKEN


def test_a_prediction_cannot_be_edited_after_it_is_made() -> None:
    """PREDICTIONS.md: never edit a prediction after you have seen output. The
    type enforces the rule rather than trusting the operator."""
    prediction = _p99_at_250rps()

    with pytest.raises(ValidationError):
        prediction.value = 1.0


def test_unknown_fields_are_rejected_rather_than_silently_dropped() -> None:
    """A model emitting `confidence=0.9` should be corrected, not quietly
    stripped of the field it thought it was providing."""
    with pytest.raises(ValidationError, match="confidence"):
        Prediction(
            metric="p99",
            comparator=Comparator.AT_LEAST,
            value=1.0,
            unit="ms",
            condition="c",
            confidence=0.9,  # type: ignore[call-arg]
        )
