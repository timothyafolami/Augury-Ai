"""The perfect-score attack works again, one epsilon from the old guard.

`tests/test_metric_gaming.py` records that a reviewer emitting only
`p99 >= 0ms` scored 1.000 on both headline metrics while saying nothing, and
beat an honest reviewer. The fix pinned the guard to the literal values from
that attack -- `<= 0` and `>= 1e12` -- rather than to the range a measurement
can actually land in.

So `p99 >= 0.000001ms` passes the gate and hits every measurement, and
`p99 <= 999999999ms` does too. The attack is restored by moving one epsilon.

A threshold has to exclude some part of the outcome space *that can occur*.
Zero is not the boundary of that space; the smallest measurement anyone would
record is.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from augury.core.schemas import Comparator, Prediction


def _claim(**over: object) -> Prediction:
    fields: dict[str, object] = {
        "metric": "http_req_duration_p99",
        "comparator": Comparator.AT_LEAST,
        "value": 250.0,
        "unit": "ms",
        "condition": "at 250rps for 60s",
    }
    fields.update(over)
    return Prediction(**fields)  # type: ignore[arg-type]


def test_a_threshold_a_hair_above_zero_is_still_vacuous() -> None:
    """The original attack, moved by one epsilon."""
    with pytest.raises(ValidationError, match="vacuous"):
        _claim(value=1e-6)


def test_a_millisecond_threshold_below_the_finest_thing_measured_is_vacuous() -> None:
    with pytest.raises(ValidationError, match="vacuous"):
        _claim(value=0.001)


def test_a_ceiling_just_under_the_old_one_is_still_vacuous() -> None:
    with pytest.raises(ValidationError, match="vacuous"):
        _claim(comparator=Comparator.AT_MOST, value=999_999_999.0)


def test_a_count_of_at_least_one_excludes_nothing_that_happens() -> None:
    """ "at least 1 query" is true of every request that touches the database."""
    with pytest.raises(ValidationError, match="vacuous"):
        _claim(
            metric="queries_per_request", comparator=Comparator.AT_LEAST, value=1.0, unit="queries"
        )


def test_a_real_latency_claim_is_still_accepted() -> None:
    assert _claim(value=250.0).value == 250.0


def test_a_real_query_count_claim_is_still_accepted() -> None:
    claim = _claim(
        metric="queries_per_request", comparator=Comparator.AT_LEAST, value=51.0, unit="queries"
    )
    assert claim.value == 51.0


def test_a_real_ceiling_is_still_accepted() -> None:
    assert _claim(comparator=Comparator.AT_MOST, value=100.0).value == 100.0


def test_an_unknown_unit_falls_back_to_excluding_only_zero() -> None:
    """A unit nobody anticipated must not be rejected for being unfamiliar."""
    assert _claim(value=0.5, unit="widgets").value == 0.5


def test_no_accepted_threshold_hits_every_plausible_measurement() -> None:
    """The property the individual cases are instances of.

    If a claim scores Hit against the smallest and the largest measurement
    anyone could record in its unit, it excluded nothing.
    """
    from augury.core.schemas import Outcome

    for value in (1e-9, 1e-6, 0.001, 0.5, 1.0, 250.0, 1e6, 1e9, 1e11):
        for comparator in (Comparator.AT_LEAST, Comparator.AT_MOST):
            try:
                claim = _claim(comparator=comparator, value=value)
            except ValidationError:
                continue
            outcomes = {claim.score(m) for m in (0.4, 12.0, 350.0, 9000.0, 1e7)}
            assert outcomes != {Outcome.HIT}, (
                f"{comparator.value} {value}{claim.unit} was accepted and hits everything"
            )
