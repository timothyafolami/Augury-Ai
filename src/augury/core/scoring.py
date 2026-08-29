"""Turn a report into the numbers the evaluation compares.

Every rate is reported with its denominator, and a rate over an empty set is
`None` rather than zero or one. A reviewer that finds nothing must not top the
table on a technicality, and a sample of one must not read like a trend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from augury.core.findings import Finding, Report
from augury.core.schemas import Outcome


class Score(BaseModel):
    """The measured result of one review.

    Carries its own identity. Without it, two of the many scores in a sweep
    cannot be shown to be over the same case, arm, seed and model -- which is
    the one thing the results table claims.
    """

    model_config = ConfigDict(frozen=True)

    case: str
    arm: str
    seed: int
    model_id: str

    seeded: int = Field(default=0, description="How many defects this case seeds")
    found: int = Field(default=0, description="How many of them this review found")
    failed: bool = Field(
        default=False, description="The review did not complete. Recorded, never dropped."
    )

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


def score(
    report: Report,
    *,
    case: str,
    arm: str,
    seed: int = 0,
    seeded: int = 0,
    found: int = 0,
    failed: bool = False,
) -> Score:
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
        case=case,
        arm=arm,
        seed=seed,
        model_id=report.model_id,
        seeded=seeded,
        found=found,
        failed=failed,
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


# A ratio over fewer measurements than this is not a rate, and printing it
# beside a ratio over fifty invites exactly the wrong comparison. Measured on
# B01, one baseline seed produced a hit rate of 1.000 from a single tested
# prediction. The counts are always reported, so withholding the ratio hides
# nothing: a reader can still see one of one and judge it themselves.
MIN_TESTED_FOR_A_RATE = 5


class ArmScore(BaseModel):
    """One arm's result across a case set.

    Rates are pooled over summed counts, never averaged across cases: a case
    with one observation must not outvote a case with a hundred. The per-case
    spread is reported beside each rate so a pooled number cannot hide one case
    carrying the whole result.
    """

    model_config = ConfigDict(frozen=True)

    arm: str
    cases: int
    model_ids: tuple[str, ...]

    seeded: int
    found: int
    failed: int
    detection_rate: float | None

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

    per_case_low: float | None
    per_case_high: float | None

    usd: float
    seconds: float


def aggregate(scores: list[Score]) -> ArmScore:
    """Combine one arm's per-case scores into the row a reader compares."""
    if not scores:
        raise ValueError("no scores to aggregate: an empty arm has no result")

    arms = {s.arm for s in scores}
    if len(arms) > 1:
        raise ValueError(f"cannot aggregate more than one arm: {sorted(arms)}")

    observations = sum(s.total_findings + s.dropped for s in scores)
    falsifiable = sum(s.falsifiable for s in scores)
    tested = sum(s.tested for s in scores)
    hits = sum(s.hits for s in scores)
    per_case = [s.falsifiable_precision for s in scores if s.falsifiable_precision is not None]

    return ArmScore(
        arm=arms.pop(),
        cases=len(scores),
        model_ids=tuple(sorted({s.model_id for s in scores})),
        seeded=sum(s.seeded for s in scores),
        found=sum(s.found for s in scores),
        failed=sum(1 for s in scores if s.failed),
        # Pooled over every seeded defect, including those in cases that
        # failed. A run that crashed found nothing, and excluding it would
        # reward crashing.
        detection_rate=_ratio(sum(s.found for s in scores), sum(s.seeded for s in scores)),
        total_findings=sum(s.total_findings for s in scores),
        falsifiable=falsifiable,
        tested=tested,
        experiments=sum(s.experiments for s in scores),
        hits=hits,
        broken=sum(s.broken for s in scores),
        dropped=sum(s.dropped for s in scores),
        falsifiable_precision=_ratio(falsifiable, observations),
        hit_rate=_ratio(hits, tested) if tested >= MIN_TESTED_FOR_A_RATE else None,
        prediction_coverage=_ratio(tested, falsifiable),
        per_case_low=min(per_case) if per_case else None,
        per_case_high=max(per_case) if per_case else None,
        usd=sum(s.usd for s in scores),
        seconds=sum(s.seconds for s in scores),
    )
