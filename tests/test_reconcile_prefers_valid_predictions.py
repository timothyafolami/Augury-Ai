"""A malformed sibling must not destroy a valid prediction.

`_strictest` ranks BETWEEN predictions by band width and takes the narrowest.
The shapes the validator rejects -- an upper bound at or below the lower, or a
missing upper -- have width zero or less, so they rank best. `reconcile` runs
on the draft, before validation, so the selector picked the prediction the
validator was about to reject and discarded the valid sibling with it.

Only an arm that produces two findings at the same construct can hit this, so
it fell on the pipeline alone: a harness-caused difference between arms rather
than a reviewer-caused one.
"""

from __future__ import annotations

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport, to_report
from augury.core.findings import Severity
from augury.core.schemas import Comparator
from augury.evaluation.reconcile import reconcile


def _draft(prediction: DraftPrediction) -> DraftFinding:
    return DraftFinding(
        path="app/api/orders.py",
        line=1,
        layer="data",
        symbol="list_orders",
        mechanism="An N+1 across the serializer.",
        severity=Severity.HIGH,
        remediation="Join the query.",
        arithmetic="",
        prediction=prediction,
    )


def _band(value: float, upper: float | None) -> DraftPrediction:
    return DraftPrediction(
        metric="queries_per_request",
        comparator=Comparator.BETWEEN,
        value=value,
        upper=upper,
        unit="queries",
        condition="50 orders",
    )


GOOD = _band(50, 200)


def _precision(*predictions: DraftPrediction) -> float | None:
    report = to_report(reconcile(DraftReport(findings=[_draft(p) for p in predictions])))
    return (
        None
        if not report.findings
        else len([f for f in report.findings if f.is_falsifiable]) / len(report.findings)
    )


def test_a_valid_band_alone_survives() -> None:
    assert _precision(GOOD) == 1.0


def test_an_inverted_sibling_does_not_take_the_valid_band_with_it() -> None:
    # upper <= value: width zero, so it used to rank as the narrowest band.
    assert _precision(GOOD, _band(101, 100)) == 1.0


def test_a_sibling_with_no_upper_bound_does_not_either() -> None:
    assert _precision(GOOD, _band(101, None)) == 1.0


def test_a_genuinely_narrower_valid_band_still_wins() -> None:
    """The guard must not disable the preference it was added to protect."""
    report = to_report(reconcile(DraftReport(findings=[_draft(GOOD), _draft(_band(90, 100))])))
    prediction = report.findings[0].prediction
    assert prediction is not None
    assert (prediction.value, prediction.upper) == (90, 100)
