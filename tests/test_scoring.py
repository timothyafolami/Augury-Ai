"""Falsifiable Precision is the headline number.

Every AI reviewer on the market emits fluent, unfalsifiable observations. The
claim this project makes is that its output carries numbers you can test, so
the share of findings that do is the number that has to be measured honestly --
including when it is bad.
"""

import pytest

from augury.core.findings import Finding, Report, Severity
from augury.core.schemas import Comparator, Outcome, Prediction
from augury.core.scoring import score


def prediction() -> Prediction:
    return Prediction(
        metric="http_req_duration_p99",
        comparator=Comparator.AT_LEAST,
        value=1000.0,
        unit="ms",
        condition="rate=250rps",
    )


def finding(*, falsifiable: bool, verdict: Outcome | None = None) -> Finding:
    return Finding(
        path="app/db.py",
        line=31,
        layer="data",
        symbol="get_session",
        mechanism="pool_size=5 against 8 workers",
        severity=Severity.HIGH,
        remediation="raise pool_size to 20",
        prediction=prediction() if falsifiable else None,
        verdict=verdict,
    )


def test_falsifiable_precision_is_the_share_carrying_a_prediction() -> None:
    report = Report(
        findings=[
            finding(falsifiable=True),
            finding(falsifiable=True),
            finding(falsifiable=False),
            finding(falsifiable=False),
        ]
    )

    assert score(report).falsifiable_precision == 0.5


def test_precision_is_undefined_rather_than_perfect_when_nothing_was_found() -> None:
    """Zero of zero is not 100%. Reporting it as 1.0 would let a reviewer that
    finds nothing top the table."""
    assert score(Report(findings=[])).falsifiable_precision is None


def test_hit_rate_counts_only_predictions_that_were_actually_tested() -> None:
    """An untested prediction is not evidence. Counting it would let the
    reviewer grade its own homework."""
    report = Report(
        findings=[
            finding(falsifiable=True, verdict=Outcome.HIT),
            finding(falsifiable=True, verdict=Outcome.MISS),
            finding(falsifiable=True, verdict=None),
        ]
    )

    assert score(report).hit_rate == 0.5


def test_a_broken_experiment_is_excluded_from_the_hit_rate() -> None:
    """Broken means the experiment did not run, so the prediction was never
    tested. Counting it either way would misreport the reviewer."""
    report = Report(
        findings=[
            finding(falsifiable=True, verdict=Outcome.HIT),
            finding(falsifiable=True, verdict=Outcome.BROKEN),
        ]
    )

    result = score(report)

    assert result.hit_rate == 1.0
    assert result.broken == 1


def test_counts_are_reported_alongside_every_rate() -> None:
    """A rate without its denominator hides a sample of one."""
    report = Report(findings=[finding(falsifiable=True, verdict=Outcome.HIT)])

    result = score(report)

    assert result.total_findings == 1
    assert result.falsifiable == 1
    assert result.tested == 1


def test_dropped_findings_are_counted_not_hidden() -> None:
    """The refiner drops what it cannot make falsifiable. That number is part
    of the result, not an embarrassment to omit."""
    report = Report(
        findings=[finding(falsifiable=True)],
        dropped=[{"claim": "consider adding a timeout", "reason": "no threshold derivable"}],
    )

    assert score(report).dropped == 1


def test_scoring_never_divides_by_zero() -> None:
    result = score(Report(findings=[]))

    assert result.hit_rate is None
    assert result.falsifiable_precision is None
    assert result.total_findings == 0


@pytest.mark.parametrize("verdict", [Outcome.HIT, Outcome.MISS])
def test_an_unfalsifiable_finding_cannot_carry_a_verdict(verdict: Outcome) -> None:
    """Nothing was predicted, so nothing could have been tested."""
    with pytest.raises(ValueError, match="prediction"):
        Finding(
            path="a.py",
            line=1,
            layer="data",
            symbol="f",
            mechanism="m",
            severity=Severity.LOW,
            remediation="r",
            prediction=None,
            verdict=verdict,
        )
