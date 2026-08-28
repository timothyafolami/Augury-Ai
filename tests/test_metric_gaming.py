"""A metric that rewards saying nothing is worse than no metric.

Every assertion here comes from an attack that worked. An adversarial review
constructed a reviewer that emits only `p99 >= 0ms` and scored it 1.000 on both
headline numbers while an honest reviewer scored 0.529 and 0.667. These tests
exist so that reviewer loses.
"""

import pytest
from pydantic import ValidationError

from augury.core.findings import Dropped, Finding, Measurement, Report, Severity
from augury.core.schemas import Comparator, Outcome, Prediction
from augury.core.scoring import score


def prediction(**overrides: object) -> Prediction:
    fields: dict[str, object] = {
        "metric": "http_req_duration_p99",
        "comparator": Comparator.AT_LEAST,
        "value": 1000.0,
        "unit": "ms",
        "condition": "rate=250rps",
    }
    return Prediction(**{**fields, **overrides})  # type: ignore[arg-type]


def finding(*, pred: Prediction | None = None, measurement: Measurement | None = None) -> Finding:
    return Finding(
        path="app/db.py",
        line=31,
        layer="data",
        symbol="get_session",
        mechanism="pool_size=5 against 8 workers",
        severity=Severity.HIGH,
        remediation="raise pool_size to 20",
        prediction=pred,
        measurement=measurement,
    )


# -- ADV-01: a claim no measurement can refute ----------------------------


def test_a_threshold_of_zero_is_not_a_prediction() -> None:
    """Every latency, count and rate is at least zero. `p99 >= 0ms` is HIT for
    every physically realisable measurement, so it excludes nothing."""
    with pytest.raises(ValidationError, match="vacuous"):
        prediction(value=0.0)


def test_a_threshold_no_measurement_could_exceed_is_not_a_prediction() -> None:
    """The mirror of the above. `p99 <= 1e308 ms` is likewise always HIT."""
    with pytest.raises(ValidationError, match="vacuous"):
        prediction(comparator=Comparator.AT_MOST, value=1e12)


def test_a_band_spanning_orders_of_magnitude_is_not_a_prediction() -> None:
    """A range is honest when it is wide because the mechanism is uncertain.
    It stops being a claim when almost every outcome falls inside it."""
    with pytest.raises(ValidationError, match="vacuous"):
        prediction(comparator=Comparator.BETWEEN, value=0.001, upper=1e9)


def test_a_genuinely_uncertain_range_is_still_allowed() -> None:
    """8 to 27 times is a real prediction: wide, honest, and refutable."""
    assert prediction(comparator=Comparator.BETWEEN, value=8.0, upper=27.0)


# -- ADV-02: the denominator that decides the headline --------------------


def test_dropped_findings_stay_in_the_precision_denominator() -> None:
    """Otherwise a pipeline with a Refiner scores 1.0 by construction: it
    drops everything it cannot quantify and divides by what is left. The
    baseline has no Refiner, so it would lose by architecture rather than
    on merit, and the comparison would mean nothing."""
    report = Report(
        findings=(finding(pred=prediction()),),
        dropped=tuple(
            Dropped(symbol="s", path="p.py", reason="no threshold derivable") for _ in range(17)
        ),
    )

    assert score(report).falsifiable_precision == pytest.approx(1 / 18)


# -- ADV-03: the reviewer must not grade its own homework -----------------


def test_a_verdict_is_derived_from_the_measurement_not_asserted() -> None:
    """Nothing may state HIT while the measurement says otherwise."""
    below = finding(pred=prediction(), measurement=Measurement(value=400.0))

    assert below.verdict is Outcome.MISS


def test_an_experiment_that_produced_no_number_is_broken() -> None:
    ran_but_failed = finding(pred=prediction(), measurement=Measurement(value=None))

    assert ran_but_failed.verdict is Outcome.BROKEN


def test_an_untested_prediction_has_no_verdict_at_all() -> None:
    assert finding(pred=prediction()).verdict is None


def test_a_measurement_without_a_prediction_is_refused() -> None:
    with pytest.raises(ValidationError, match="prediction"):
        finding(measurement=Measurement(value=1.0))


# -- ADV-04: a prediction may not be edited after the experiment ----------


def test_a_finding_cannot_be_rewritten_once_made() -> None:
    """PREDICTIONS.md: never edit a prediction after you have seen output.
    Freezing Prediction alone was not enough, because the reference to it was
    swappable."""
    made = finding(pred=prediction(), measurement=Measurement(value=400.0))

    with pytest.raises(ValidationError):
        made.prediction = prediction(comparator=Comparator.AT_MOST, value=1e6)


def test_a_report_cannot_have_its_misses_removed() -> None:
    report = Report(findings=(finding(pred=prediction(), measurement=Measurement(value=1200.0)),))

    with pytest.raises(ValidationError):
        report.findings = ()


# -- ADV-05: the denominator must not be chosen by the graded component ----


def test_prediction_coverage_is_reported_so_a_tiny_sample_cannot_hide() -> None:
    """100% over one of a hundred predictions must not render like 100% over
    a hundred. Without this, abandoning any experiment trending toward MISS
    is free."""
    report = Report(
        findings=(
            finding(pred=prediction(), measurement=Measurement(value=1200.0)),
            *(finding(pred=prediction()) for _ in range(99)),
        )
    )

    result = score(report)

    assert result.hit_rate == 1.0
    assert result.prediction_coverage == pytest.approx(0.01)


# -- ADV-07: one experiment is one test -----------------------------------


def test_one_experiment_answering_twenty_findings_counts_once() -> None:
    """A specialist that enumerates twenty call sites of one mechanism gets
    one k6 run. Reporting n=20 would inflate the denominator that makes the
    hit rate credible by the reviewer's own verbosity."""
    same = [finding(pred=prediction(), measurement=Measurement(value=1200.0)) for _ in range(20)]

    result = score(Report(findings=tuple(same)))

    assert result.experiments == 1
    assert result.tested == 20
