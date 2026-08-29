"""The hit rate is a rate over experiments, not over findings.

`_distinct_experiments` exists because "one k6 run can answer twenty findings
that share a mechanism. Counting it twenty times inflates the denominator that
makes the hit rate credible by the reviewer's own verbosity." That reasoning
was applied to the gate that decides whether a rate may be published, and not
to the rate itself.

It matters on the published run: two of the pipeline's B01 findings both
predict `queries_per_request` and are both settled by the single measurement
`B01/queries_per_request`. One experiment moved two units on one arm and one on
the other.
"""

from __future__ import annotations

from augury.core.findings import Finding, Measurement, Report, Severity
from augury.core.schemas import Comparator, Prediction
from augury.core.scoring import score


def _finding(symbol: str, *, value: float, measured: float, experiment: str) -> Finding:
    return Finding(
        path="app/api/orders.py",
        line=1,
        layer="data",
        symbol=symbol,
        mechanism="An N+1 across the serializer.",
        severity=Severity.HIGH,
        remediation="Join the query.",
        prediction=Prediction(
            metric="queries_per_request",
            comparator=Comparator.AT_LEAST,
            value=value,
            unit="queries",
            condition="50 orders",
        ),
        measurement=Measurement(value=measured, experiment=experiment),
    )


def _score(report: Report) -> tuple[int, int, float | None]:
    s = score(report, case="B01", arm="a", seed=0, seeded=1, found=1, failed=False)
    return s.hits, s.tested, s.hit_rate


def test_two_findings_settled_by_one_experiment_count_once() -> None:
    report = Report(
        findings=(
            _finding("list_orders", value=40, measured=51, experiment="B01/queries_per_request"),
            _finding(
                "serialize_order", value=40, measured=51, experiment="B01/queries_per_request"
            ),
        )
    )
    assert _score(report) == (1, 1, 1.0)


def test_findings_settled_by_different_experiments_count_separately() -> None:
    report = Report(
        findings=(
            _finding("list_orders", value=40, measured=51, experiment="B01/queries_per_request"),
            _finding("charge", value=2, measured=3, experiment="B01/retry_amplification"),
        )
    )
    assert _score(report) == (2, 2, 1.0)


def test_one_experiment_settling_a_right_and_a_wrong_claim_is_not_a_hit() -> None:
    """The arm was not right about that mechanism, so it does not score one.

    Counting it as a hit would let an arm buy a hit by pairing every correct
    prediction with a wrong one settled by the same run.
    """
    report = Report(
        findings=(
            _finding("list_orders", value=40, measured=51, experiment="B01/queries_per_request"),
            _finding(
                "serialize_order", value=99, measured=51, experiment="B01/queries_per_request"
            ),
        )
    )
    assert _score(report) == (0, 1, 0.0)
