"""Repeating an arm, because one run is not a measurement.

A single run of each arm on case B01 gave the baseline 5 of 5 and then 4 of 5,
at temperature zero. Either number, reported alone, would have been noise
presented as a result. So an arm is run several times and the spread is
reported beside the mean, and a difference smaller than the variance is named
inconclusive rather than argued for.
"""

from __future__ import annotations

from statistics import fmean

from pydantic import BaseModel, ConfigDict

from augury.core.scoring import Score, aggregate


class SweepResult(BaseModel):
    """One arm, run several times."""

    model_config = ConfigDict(frozen=True)

    arm: str
    seeds: int
    failed: int

    recall_mean: float | None
    recall_low: float | None
    recall_high: float | None

    # Pooled across seeds rather than averaged. A single run of a case yields
    # too few distinct experiments to support a rate, so every per-seed value
    # is withheld and averaging withheld values gives nothing. Pooling is how
    # the floor is reached honestly.
    hits: int
    tested: int
    experiments: int
    hit_rate: float | None

    precision_mean: float | None
    usd_mean: float
    seconds_mean: float

    @property
    def repeated(self) -> bool:
        """A single run is reported, but never as though it were repeated."""
        return self.seeds > 1

    @staticmethod
    def compare(left: SweepResult, right: SweepResult) -> str:
        """Whether `left` beat `right`, or whether the run cannot say.

        Ranges that overlap mean the arms were not distinguished. Calling that
        a win is how a submission ends up defending a number it cannot support.
        """
        if (
            left.recall_low is None
            or left.recall_high is None
            or right.recall_low is None
            or right.recall_high is None
        ):
            return "inconclusive"
        if left.recall_low > right.recall_high:
            return "better"
        if left.recall_high < right.recall_low:
            return "worse"
        return "inconclusive"


def summarise(scores: list[Score]) -> SweepResult:
    """Combine repeated runs of one arm into a result with its spread."""
    if not scores:
        raise ValueError("no scores to summarise")

    arms = {s.arm for s in scores}
    if len(arms) > 1:
        raise ValueError(f"a sweep is one arm, not {sorted(arms)}")

    by_seed: dict[int, list[Score]] = {}
    for entry in scores:
        by_seed.setdefault(entry.seed, []).append(entry)

    per_seed = [aggregate(runs) for runs in by_seed.values()]
    recalls = [run.detection_rate for run in per_seed if run.detection_rate is not None]
    precisions = [
        run.falsifiable_precision for run in per_seed if run.falsifiable_precision is not None
    ]

    pooled = aggregate(scores)

    failures = sum(1 for entry in scores if entry.failed)
    # A run in which every review crashed has no recall. Reporting 0.000 for it
    # would be a fabricated result, and its zero spread is the same signature a
    # perfectly steady arm produces.
    completed = failures < len(scores)

    return SweepResult(
        arm=arms.pop(),
        seeds=len(by_seed),
        failed=failures,
        hits=pooled.hits,
        tested=pooled.tested,
        experiments=pooled.experiments,
        hit_rate=pooled.hit_rate,
        recall_mean=fmean(recalls) if recalls and completed else None,
        recall_low=min(recalls) if recalls and completed else None,
        recall_high=max(recalls) if recalls and completed else None,
        precision_mean=fmean(precisions) if precisions else None,
        usd_mean=fmean(run.usd for run in per_seed),
        seconds_mean=fmean(run.seconds for run in per_seed),
    )
