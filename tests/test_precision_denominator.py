"""A finding must count once, however many lists it appears in.

`to_report` keeps a finding whose prediction failed validation *and* records a
`Dropped` for it, and `aggregate` computed the denominator as
`len(findings) + len(dropped)`. So a malformed prediction cost two
observations while a finding with no prediction at all cost one -- the model
was penalised harder for trying and failing than for not trying.

`Dropped` exists to stop a reviewer gaming precision by deleting whatever it
cannot quantify and dividing by the remainder. That intent needs dropped
entries counted only when they are *not* already present as findings.
"""

from __future__ import annotations

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport, to_report
from augury.core.findings import Dropped, Finding, Report, Severity
from augury.core.schemas import Comparator, Prediction
from augury.core.scoring import aggregate, score


def _draft(prediction: DraftPrediction | None) -> DraftFinding:
    return DraftFinding(
        path="app/db.py",
        line=3,
        layer="data",
        symbol="engine",
        mechanism="Pool is smaller than the worker count.",
        severity=Severity.HIGH,
        remediation="Raise pool_size to match.",
        arithmetic="",
        prediction=prediction,
    )


VACUOUS = DraftPrediction(
    metric="active_connections",
    comparator=Comparator.AT_LEAST,
    value=0.0,  # every magnitude is at least zero: not a prediction
    upper=None,
    unit="count",
    condition="any load",
)


def _score(report: Report) -> float | None:
    return score(
        report, case="B01", arm="a", seed=0, seeded=1, found=0, failed=False
    ).falsifiable_precision


GOOD = DraftPrediction(
    metric="active_connections",
    comparator=Comparator.AT_LEAST,
    value=40.0,
    upper=None,
    unit="count",
    condition="200 concurrent requests",
)


def test_one_malformed_prediction_is_one_observation_not_two() -> None:
    """One good and one vacuous is one out of two, not one out of three.

    A denominator of zero-falsifiable findings cannot detect this -- 0/1 and
    0/2 are both 0.0 -- so the good prediction is what makes the test able to
    fail.
    """
    report = to_report(DraftReport(findings=[_draft(GOOD), _draft(VACUOUS)]))
    assert len(report.findings) == 2
    assert len(report.dropped) == 1
    assert _score(report) == 0.5

    # And a malformed prediction costs exactly what an absent one costs: both
    # are one observation that produced nothing testable.
    absent = to_report(DraftReport(findings=[_draft(GOOD), _draft(None)]))
    assert _score(absent) == _score(report)


def test_a_dropped_entry_with_no_finding_still_counts() -> None:
    """The anti-gaming intent, preserved.

    A reviewer that deletes what it cannot quantify must not be scored on the
    remainder, so a Dropped naming something absent from findings adds to the
    denominator.
    """
    good = Prediction(
        metric="active_connections",
        comparator=Comparator.AT_LEAST,
        value=40,
        unit="count",
        condition="200 concurrent requests",
    )
    report = Report(
        findings=(
            Finding(
                path="a.py",
                line=1,
                layer="data",
                symbol="kept",
                mechanism="m",
                severity=Severity.LOW,
                remediation="r",
                prediction=good,
            ),
        ),
        dropped=(Dropped(symbol="deleted", path="b.py", reason="not quantifiable"),),
    )
    assert _score(report) == 0.5


def test_aggregate_agrees_with_the_single_score() -> None:
    report = to_report(DraftReport(findings=[_draft(VACUOUS)]))
    single = score(report, case="B01", arm="a", seed=0, seeded=1, found=0, failed=False)
    assert aggregate([single]).falsifiable_precision == 0.0
