"""Turn a report into the numbers the evaluation compares.

Every rate is reported with its denominator, and a rate over an empty set is
`None` rather than zero or one. A reviewer that finds nothing must not top the
table on a technicality, and a sample of one must not read like a trend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from augury.core.findings import Report
from augury.core.schemas import Outcome


class Score(BaseModel):
    """The measured result of one review."""

    model_config = ConfigDict(frozen=True)

    total_findings: int
    falsifiable: int
    tested: int
    hits: int
    broken: int
    dropped: int

    falsifiable_precision: float | None
    hit_rate: float | None

    usd: float
    seconds: float


def score(report: Report) -> Score:
    """Measure one report. No rate is invented where there is nothing to divide."""
    findings = report.findings
    falsifiable = [f for f in findings if f.is_falsifiable]
    tested = [f for f in falsifiable if f.was_tested]
    hits = [f for f in tested if f.verdict is Outcome.HIT]
    broken = [f for f in falsifiable if f.verdict is Outcome.BROKEN]

    return Score(
        total_findings=len(findings),
        falsifiable=len(falsifiable),
        tested=len(tested),
        hits=len(hits),
        broken=len(broken),
        dropped=len(report.dropped),
        falsifiable_precision=_ratio(len(falsifiable), len(findings)),
        hit_rate=_ratio(len(hits), len(tested)),
        usd=report.usd,
        seconds=report.seconds,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    """None when there is nothing to divide, so an empty run reads as absent."""
    return numerator / denominator if denominator else None
