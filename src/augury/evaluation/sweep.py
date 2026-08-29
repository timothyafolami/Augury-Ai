"""Repeating an arm, because one run is not a measurement.

A single run of each arm on case B01 gave the baseline 5 of 5 and then 4 of 5,
at temperature zero. Either number, reported alone, would have been noise
presented as a result. So an arm is run several times and the spread is
reported beside the mean, and a difference smaller than the variance is named
inconclusive rather than argued for.
"""

from __future__ import annotations

from statistics import fmean
from typing import cast

from pydantic import BaseModel, ConfigDict

from augury.core.scoring import Score, aggregate
from augury.evaluation.significance import fisher_exact, permutation_p


class SweepResult(BaseModel):
    """One arm, run several times."""

    model_config = ConfigDict(frozen=True)

    arm: str
    seeds: int
    failed: int

    independent: bool = True
    """Whether the repeats were independent observations.

    False under replay, where every repeat is served from the same recording
    and the arm was therefore observed exactly once however many times it was
    asked. A range built from non-independent repeats has zero width for a
    reason that has nothing to do with the arm being reliable.
    """

    recall_mean: float | None
    recall_low: float | None
    recall_high: float | None
    recalls: tuple[float, ...] = ()
    """Recall per repeat, kept so the permutation test has something to permute.

    Only the range was retained, so `permutation_p` -- defined, tested, and
    reported in the hot take -- was computable by no shipped command.
    """

    # Pooled across seeds rather than averaged. A single run of a case yields
    # too few distinct experiments to support a rate, so every per-seed value
    # is withheld and averaging withheld values gives nothing. Pooling is how
    # the floor is reached honestly.
    hits: int
    tested: int
    experiments: int
    hit_rate: float | None

    precision_mean: float | None
    coverage_mean: float | None = None
    """Share of falsifiable claims that any experiment could grade.

    Printed beside the hit rate because the hit rate is a rate over the claims
    that reached a measurement, and an arm aiming at metrics no case measures
    is scored only on its best-aimed claims at no cost for the rest.
    """
    broken: int = 0
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

        **Repeats that were not independent cannot separate anything at all.**
        Replay serves every repeat from one recording, so five repeats collapse
        to a single observation and both arms report a range like 0.700-0.700.
        Those do not overlap, and this method called it "better" -- the pipeline
        beating the baseline on recall, concluded from one observation each.

        Note what is *not* disqualifying: a zero-width range from genuinely
        independent repeats. Three live runs that all returned 1/5 against three
        that all returned 5/5 is real evidence, and refusing it would throw away
        the comparison this method exists to make. The defect is the repeats
        being the same observation, not the numbers agreeing.
        """
        if not (left.independent and right.independent):
            return "inconclusive"

        bounds = (left.recall_low, left.recall_high, right.recall_low, right.recall_high)
        if any(bound is None for bound in bounds):
            return "inconclusive"
        low_l, high_l, low_r, high_r = cast("tuple[float, float, float, float]", bounds)

        if low_l > high_r:
            return "better"
        if high_l < low_r:
            return "worse"
        return "inconclusive"


def summarise(scores: list[Score], *, independent: bool = True) -> SweepResult:
    """Combine repeated runs of one arm into a result with its spread.

    `independent` is False under replay, where the repeats are one recording
    served several times and the spread between them is therefore not a
    measurement of anything.
    """
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

    # Pooling assumes each repeat is a new observation. Under replay -- and
    # under record, where repeats two onward hit the cassette written by the
    # first -- they are one observation served again, so pooling multiplied
    # every count by the repeat number and gave `25 / 30` for `5 / 6`. That
    # inflation is what turned a Fisher p of 1.0000 into a published 0.052.
    counted = scores if independent else next(iter(by_seed.values()))
    pooled = aggregate(counted)

    failures = sum(1 for entry in scores if entry.failed)
    # A run in which every review crashed has no recall. Reporting 0.000 for it
    # would be a fabricated result, and its zero spread is the same signature a
    # perfectly steady arm produces.
    completed = failures < len(scores)

    return SweepResult(
        arm=arms.pop(),
        seeds=len(by_seed),
        independent=independent,
        recalls=tuple(recalls),
        failed=failures,
        hits=pooled.hits,
        tested=pooled.tested,
        experiments=pooled.experiments,
        hit_rate=pooled.hit_rate,
        recall_mean=fmean(recalls) if recalls and completed else None,
        recall_low=min(recalls) if recalls and completed else None,
        recall_high=max(recalls) if recalls and completed else None,
        precision_mean=fmean(precisions) if precisions else None,
        coverage_mean=pooled.prediction_coverage,
        broken=pooled.broken,
        # Recording pays for the first repeat and replays the rest, so the mean
        # over repeats is a fifth of what one sweep actually costs.
        usd_mean=fmean(run.usd for run in per_seed) if independent else per_seed[0].usd,
        seconds_mean=(
            fmean(run.seconds for run in per_seed) if independent else per_seed[0].seconds
        ),
    )


def recall_permutation_p(left: SweepResult, right: SweepResult) -> float | None:
    """The permutation probability for recall, or None when it would mislead.

    Withheld for the same reason `compare` refuses a verdict: replay repeats one
    observation, and permuting five copies of 0.800 against five copies of 0.700
    returns p = 0.0079. A spurious range is visibly a range; a spurious p-value
    reads as a finding.
    """
    if not (left.independent and right.independent):
        return None
    return permutation_p(list(left.recalls), list(right.recalls))


def hit_rate_fisher_p(left: SweepResult, right: SweepResult) -> float | None:
    """Fisher's exact test on the hit rates, or None when it would mislead.

    Guarded exactly as `compare` and `recall_permutation_p` are. This one was
    not, and it was the one that mattered: it was handed pooled counts from
    five replayed repeats and reported p = 0.052 for an observation whose
    honest p is 1.0000.
    """
    if not (left.independent and right.independent):
        return None
    return fisher_exact(
        hits_a=left.hits, tested_a=left.tested, hits_b=right.hits, tested_b=right.tested
    )
