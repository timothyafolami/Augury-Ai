"""What a model returns, and how it becomes a finding.

The baseline and the full pipeline emit the same schema and are asked for the
same thing, including a prediction. Anything else would be rigging the
comparison: a baseline denied the chance to be falsifiable would lose by
construction, and the result would mean nothing.

So the gate is here, applied identically to both: a prediction survives only if
it passes the same validation. A model that fills the fields with nonsense gets
the finding counted as unfalsifiable, exactly as if it had left them empty.
"""

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport, to_report
from augury.core.findings import Severity
from augury.core.schemas import Comparator


def draft(prediction: DraftPrediction | None) -> DraftFinding:
    return DraftFinding(
        path="app/db.py",
        line=31,
        layer="data",
        symbol="get_session",
        mechanism="pool_size=5 against 8 workers",
        severity=Severity.HIGH,
        remediation="raise pool_size to 20",
        arithmetic="Little's Law at 40ms service time",
        prediction=prediction,
    )


def good_prediction() -> DraftPrediction:
    return DraftPrediction(
        metric="http_req_duration_p99",
        comparator=Comparator.AT_LEAST,
        value=1000.0,
        unit="ms",
        condition="rate=250rps",
    )


def test_a_valid_prediction_survives_conversion() -> None:
    report = to_report(DraftReport(findings=[draft(good_prediction())]))

    assert report.findings[0].is_falsifiable


def test_a_finding_with_no_prediction_is_kept_but_unfalsifiable() -> None:
    """It is still worth showing the user. It just cannot be proved."""
    report = to_report(DraftReport(findings=[draft(None)]))

    assert len(report.findings) == 1
    assert not report.findings[0].is_falsifiable


def test_an_inverted_range_is_rejected_and_the_reason_recorded() -> None:
    """A band nothing can fall inside is unfalsifiable wearing a falsifiable
    type. The model filled the fields; that is not the same as a prediction."""
    inverted = DraftPrediction(
        metric="retry_amplification",
        comparator=Comparator.BETWEEN,
        value=27.0,
        upper=8.0,
        unit="x",
        condition="3 hops",
    )

    report = to_report(DraftReport(findings=[draft(inverted)]))

    assert not report.findings[0].is_falsifiable
    assert len(report.dropped) == 1
    assert "upper" in report.dropped[0].reason


def test_an_empty_unit_is_rejected() -> None:
    """A number with no dimension is not a measurement."""
    dimensionless = DraftPrediction(
        metric="latency",
        comparator=Comparator.AT_LEAST,
        value=1.0,
        unit="",
        condition="under load",
    )

    report = to_report(DraftReport(findings=[draft(dimensionless)]))

    assert not report.findings[0].is_falsifiable


def test_a_rejected_prediction_keeps_the_finding_visible_to_the_user() -> None:
    """Silently discarding a reviewer's output is the very failure this tool
    exists to catch. The finding stays; only the claim to be testable goes."""
    bad = DraftPrediction(
        metric="", comparator=Comparator.AT_LEAST, value=1.0, unit="ms", condition="c"
    )

    report = to_report(DraftReport(findings=[draft(bad)]))

    assert report.findings[0].symbol == "get_session"
    assert report.dropped[0].symbol == "get_session"


def test_conversion_carries_the_run_metadata() -> None:
    report = to_report(
        DraftReport(findings=[draft(good_prediction())]),
        model_id="openai/gpt-oss-120b",
        usd=0.0031,
        seconds=12.5,
    )

    assert report.model_id == "openai/gpt-oss-120b"
    assert report.usd == 0.0031
