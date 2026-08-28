"""Turn a report into the numbers the evaluation compares.

Every rate is reported with its denominator, and a rate over an empty set is
`None` rather than zero or one. A reviewer that finds nothing must not top the
table on a technicality, and a sample of one must not read like a trend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from augury.core.findings import Finding, Report
from augury.core.schemas import Outcome


class Score(BaseModel):
    """The measured result of one review."""

    model_config = ConfigDict(frozen=True)

    total_findings: int
    falsifiable: int
    tested: int
    experiments: int
    hits: int
    broken: int
    dropped: int

    falsifiable_precision: float | None
    hit_rate: float | None
    prediction_coverage: float | None

    usd: float
    seconds: float


def score(report: Report) -> Score:
    """Measure one report. No rate is invented where there is nothing to divide."""
    findings = report.findings
    falsifiable = [f for f in findings if f.is_falsifiable]
    tested = [f for f in falsifiable if f.was_tested]
    hits = [f for f in tested if f.verdict is Outcome.HIT]
    broken = [f for f in falsifiable if f.verdict is Outcome.BROKEN]

    # Everything the reviewer produced, including what it could not quantify.
    # Dividing by the survivors alone would score any pipeline with a Refiner
    # at 1.0 by construction: drop what is hard, then divide by what is left.
    observations = len(findings) + len(report.dropped)

    return Score(
        total_findings=len(findings),
        falsifiable=len(falsifiable),
        tested=len(tested),
        experiments=_distinct_experiments(tested),
        hits=len(hits),
        broken=len(broken),
        dropped=len(report.dropped),
        falsifiable_precision=_ratio(len(falsifiable), observations),
        hit_rate=_ratio(len(hits), len(tested)),
        prediction_coverage=_ratio(len(tested), len(falsifiable)),
        usd=report.usd,
        seconds=report.seconds,
    )


def _distinct_experiments(tested: list[Finding]) -> int:
    """How many experiments actually ran.

    One k6 run can answer twenty findings that share a mechanism. Counting it
    twenty times inflates the denominator that makes the hit rate credible by
    the reviewer's own verbosity.
    """
    return len(
        {
            f.measurement.experiment
            or (f.prediction.metric, f.prediction.condition, f.prediction.value)
            for f in tested
            if f.measurement is not None and f.prediction is not None
        }
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    """None when there is nothing to divide, so an empty run reads as absent."""
    return numerator / denominator if denominator else None
