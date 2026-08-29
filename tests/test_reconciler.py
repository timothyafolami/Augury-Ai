"""Merging findings that collide on the same construct.

Pool exhaustion is simultaneously a network, a data and a failure concern, so
three specialists can each raise it. Three near-identical entries in a report
is a defect in the reviewer, not a thorough review: it dilutes precision, it
inflates the finding count, and it teaches the reader to skim.

Measured on case B01 before this existed: eleven findings of which four were
duplicates, and a falsifiable precision below the single-prompt baseline.
"""

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport
from augury.core.findings import Severity
from augury.core.schemas import Comparator
from augury.evaluation.reconcile import reconcile


def prediction(value: float = 1000.0) -> DraftPrediction:
    return DraftPrediction(
        metric="http_req_duration_p99",
        comparator=Comparator.AT_LEAST,
        value=value,
        upper=None,
        unit="ms",
        condition="rate=250rps",
    )


def finding(
    *,
    path: str = "app/clients/payments.py",
    symbol: str = "charge",
    layer: str = "failure",
    severity: Severity = Severity.MEDIUM,
    mechanism: str = "retries without backoff",
    pred: DraftPrediction | None = None,
) -> DraftFinding:
    return DraftFinding(
        path=path,
        line=20,
        layer=layer,
        symbol=symbol,
        mechanism=mechanism,
        severity=severity,
        remediation="add backoff",
        arithmetic="",
        prediction=pred,
    )


def test_two_specialists_on_the_same_construct_produce_one_finding() -> None:
    merged = reconcile(
        DraftReport(
            findings=[
                finding(layer="failure", mechanism="retries without backoff"),
                finding(layer="network", mechanism="the retry loop has no jitter"),
            ]
        )
    )

    assert len(merged.findings) == 1


def test_the_merged_finding_keeps_the_highest_severity() -> None:
    """A reviewer that downgrades a high-severity finding by merging it into a
    medium one has made the report worse, not shorter."""
    merged = reconcile(
        DraftReport(
            findings=[
                finding(severity=Severity.MEDIUM),
                finding(severity=Severity.HIGH, layer="network"),
            ]
        )
    )

    assert merged.findings[0].severity is Severity.HIGH


def test_the_merged_finding_credits_every_specialist_that_raised_it() -> None:
    """Agreement across concerns is evidence. Discarding it loses information
    the reader would have used."""
    merged = reconcile(DraftReport(findings=[finding(layer="failure"), finding(layer="network")]))

    assert set(merged.findings[0].layer.split("+")) == {"failure", "network"}


def test_a_falsifiable_finding_survives_a_merge_with_an_unfalsifiable_one() -> None:
    """Keeping the version without a prediction would throw away the only
    testable claim, which is the whole point of the report."""
    merged = reconcile(
        DraftReport(findings=[finding(pred=None), finding(layer="network", pred=prediction())])
    )

    assert merged.findings[0].prediction is not None


def test_the_strictest_prediction_wins_when_both_are_falsifiable() -> None:
    """A stricter threshold excludes more of the outcome space, so it is the
    more informative claim and the easier one to refute."""
    merged = reconcile(
        DraftReport(
            findings=[
                finding(pred=prediction(value=500.0)),
                finding(layer="network", pred=prediction(value=1200.0)),
            ]
        )
    )

    assert merged.findings[0].prediction is not None
    assert merged.findings[0].prediction.value == 1200.0


def test_findings_on_different_constructs_are_left_alone() -> None:
    merged = reconcile(
        DraftReport(findings=[finding(symbol="charge"), finding(symbol="quote", path="app/s.py")])
    )

    assert len(merged.findings) == 2


def test_the_same_symbol_in_a_different_file_is_a_different_finding() -> None:
    merged = reconcile(
        DraftReport(
            findings=[
                finding(path="app/a.py", symbol="get"),
                finding(path="app/b.py", symbol="get"),
            ]
        )
    )

    assert len(merged.findings) == 2


def test_reconciling_nothing_is_not_an_error() -> None:
    assert reconcile(DraftReport(findings=[])).findings == []


def test_the_mechanisms_are_combined_rather_than_one_being_dropped() -> None:
    merged = reconcile(
        DraftReport(
            findings=[
                finding(mechanism="retries without backoff"),
                finding(layer="network", mechanism="no jitter, so retries synchronise"),
            ]
        )
    )

    assert "backoff" in merged.findings[0].mechanism
    assert "jitter" in merged.findings[0].mechanism
