"""The remaining ways a number could be earned without being true.

Each of these came from an adversarial review that constructed the attack and
ran it. They are grouped here because they share one theme: a claim being
settled by evidence that is not about it.
"""

import pytest

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport, to_report
from augury.core.findings import Finding, Measurement, Report, Severity
from augury.core.schemas import Comparator, Prediction
from augury.core.scoring import aggregate, score
from augury.evaluation.reconcile import reconcile


def prediction(metric: str = "queries_per_request", **over: object) -> Prediction:
    fields: dict[str, object] = {
        "metric": metric,
        "comparator": Comparator.AT_MOST,
        "value": 2.0,
        "unit": "queries",
        "condition": "50 orders",
    }
    return Prediction(**{**fields, **over})  # type: ignore[arg-type]


def finding(**over: object) -> Finding:
    fields: dict[str, object] = {
        "path": "app/serializers.py",
        "line": 11,
        "layer": "data",
        "symbol": "serialize_order",
        "mechanism": "a query per order",
        "severity": Severity.HIGH,
        "remediation": "batch the loads",
        "prediction": prediction(),
    }
    return Finding(**{**fields, **over})  # type: ignore[arg-type]


# -- a measurement must be about the file the claim is about ---------------


def test_a_measurement_is_only_attached_where_the_experiment_applies() -> None:
    """An arm predicting `queries_per_request` about five unrelated files was
    scored a perfect hit rate off one experiment run on a sixth."""
    from augury.evaluation.prover import applies_to

    about = ("app/serializers.py",)

    assert applies_to(prediction(), path="app/serializers.py", locations=about)
    assert not applies_to(prediction(), path="app/services/pricing.py", locations=about)


def test_a_claim_about_the_decoy_file_is_not_settled_by_a_real_experiment() -> None:
    """pricing.py carries a loud FIXME and is fine. A claim about it must not
    inherit the verdict of a measurement taken elsewhere."""
    from augury.evaluation.prover import applies_to

    assert not applies_to(
        prediction(), path="app/services/pricing.py", locations=("app/serializers.py",)
    )


# -- one experiment is one measurement -------------------------------------


def test_the_rate_floor_counts_experiments_not_findings() -> None:
    """Five near-duplicate findings sharing one metric are one measurement.
    Counting them as five unlocked a rate that could only ever be 0.0 or 1.0."""
    same = tuple(
        finding(measurement=Measurement(value=51.0, experiment="B01/queries_per_request"))
        for _ in range(5)
    )

    arm = aggregate([score(Report(findings=same), case="B01", arm="a")])

    assert arm.experiments == 1
    assert arm.hit_rate is None, "one experiment cannot support a rate"


# -- reconcile must not trade a testable claim for an untestable one -------


def draft(metric: str, value: float, comparator: Comparator = Comparator.AT_LEAST) -> DraftFinding:
    return DraftFinding(
        path="app/clients/shipping.py",
        line=12,
        layer="network",
        symbol="quote",
        mechanism="no timeout",
        severity=Severity.HIGH,
        remediation="set one",
        arithmetic="",
        prediction=DraftPrediction(
            metric=metric,
            comparator=comparator,
            value=value,
            upper=None,
            unit="x",
            condition="four workers",
        ),
    )


def test_findings_about_different_metrics_are_not_merged() -> None:
    """Merging them discarded the one metric the case can actually run, and
    kept one with no experiment, guaranteeing Broken."""
    merged = reconcile(
        DraftReport(
            findings=[draft("http_req_duration_p99", 100.0), draft("worker_saturation", 1.0)]
        )
    )

    metrics = {f.prediction.metric for f in merged.findings if f.prediction}
    assert metrics == {"http_req_duration_p99", "worker_saturation"}


def test_the_strictest_at_most_claim_is_the_smallest_one() -> None:
    """A larger ceiling excludes less. Keeping it upgraded a Miss into a Hit."""
    merged = reconcile(
        DraftReport(
            findings=[
                draft("final_balance", 10.0, Comparator.AT_MOST),
                draft("final_balance", 95.0, Comparator.AT_MOST),
            ]
        )
    )

    assert merged.findings[0].prediction is not None
    assert merged.findings[0].prediction.value == 10.0


def test_reconcile_output_always_validates_as_a_report() -> None:
    """Concatenating eight specialists' prose overflowed the field length and
    raised, which zeroed an entire arm-seed and read as a genuine miss."""
    crowded = DraftReport(
        findings=[
            draft("worker_saturation", 1.0).model_copy(
                update={"layer": f"layer{index}", "mechanism": "x" * 900}
            )
            for index in range(8)
        ]
    )

    to_report(reconcile(crowded))  # must not raise


# -- an arm's results must be the arm's ------------------------------------


async def test_the_arm_label_cannot_disagree_with_the_reviewer_run() -> None:
    """One omitted keyword published baseline results under the augury name,
    and nothing downstream could detect it."""
    from augury.evaluation.runner import run_arm

    with pytest.raises(ValueError, match="reviewer"):
        await run_arm("augury", _no_model(), [], reviewer=None)  # type: ignore[arg-type]


def _no_model() -> object:
    class Unused:
        model_id = "unused"

    return Unused()
