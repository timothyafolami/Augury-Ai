"""Deciding whether a difference between two arms is a difference.

Two claims in this project's changelog were withdrawn after being read off a
pair of means. The tests live here, in the harness, so a verdict is produced by
the run rather than argued for once the numbers are in.

Exact tests rather than approximations, because the samples are small enough
that the approximations are the part that would be wrong.
"""

from __future__ import annotations

import itertools
import random
from math import comb, fsum
from statistics import fmean

SIGNIFICANCE = 0.05

# Beyond this the exhaustive enumeration stops being instant: C(2n, n) is
# 12,870 at n=8, 601 million at n=16, and 1.2e17 at n=30. The natural response
# to a p of 0.11 is more seeds, and the natural response must not be a hang.
MAX_EXACT_SAMPLE = 10
RESAMPLES = 20_000


def fisher_exact(*, hits_a: int, tested_a: int, hits_b: int, tested_b: int) -> float | None:
    """Two-sided probability of a hit-rate difference this large by chance.

    Exact rather than a chi-squared approximation: with a couple of dozen
    tested predictions per arm, the approximation's assumptions are the ones
    that fail first.
    """
    if tested_a == 0 or tested_b == 0:
        return None

    a, b = hits_a, tested_a - hits_a
    c, d = hits_b, tested_b - hits_b
    total = a + b + c + d

    def probability(successes: int) -> float:
        return comb(a + b, successes) * comb(c + d, a + c - successes) / comb(total, a + c)

    low = max(0, a + c - (c + d))
    high = min(a + b, a + c)
    observed = probability(a)

    # Every table at least as extreme as the one observed, with a tolerance so
    # floating point does not exclude the observed table from its own tail.
    return min(
        1.0,
        fsum(
            probability(x) for x in range(low, high + 1) if probability(x) <= observed * (1 + 1e-9)
        ),
    )


def permutation_p(left: list[float], right: list[float]) -> float | None:
    """Two-sided probability of a mean difference this large under relabelling.

    Enumerated exactly. With eight runs an arm this is 12,870 arrangements,
    which is cheaper than reasoning about whether a normal approximation holds.

    A small sample has a floor it cannot go below: three against three can
    reach 0.100 at best, whatever the result. That is a property of the design
    rather than of the finding, and it is why this returns a number instead of
    a verdict.
    """
    if not left or not right:
        # Matching fisher_exact, which returns None rather than a verdict. An
        # arm that lost every run to provider errors is missing data, and
        # reporting "no difference" for it would be a positive claim of
        # equivalence drawn from nothing.
        return None

    pooled = left + right
    observed = abs(fmean(left) - fmean(right))
    size = len(left)

    if size > MAX_EXACT_SAMPLE:
        return _sampled(pooled, size, observed)

    extreme = total = 0
    for chosen in itertools.combinations(range(len(pooled)), size):
        picked = set(chosen)
        one = [pooled[i] for i in chosen]
        other = [pooled[i] for i in range(len(pooled)) if i not in picked]
        total += 1
        if abs(fmean(one) - fmean(other)) >= observed - 1e-12:
            extreme += 1

    return extreme / total


def _sampled(pooled: list[float], size: int, observed: float) -> float:
    """A seeded resample, for samples too large to enumerate.

    Seeded so the published number is reproducible: an unseeded p-value is a
    number that changes when a judge re-runs it.
    """
    generator = random.Random(0)
    shuffled = list(pooled)
    extreme = 0

    for _ in range(RESAMPLES):
        generator.shuffle(shuffled)
        one, other = shuffled[:size], shuffled[size:]
        if abs(fmean(one) - fmean(other)) >= observed - 1e-12:
            extreme += 1

    return extreme / RESAMPLES


def verdict(probability: float | None) -> str:
    """What may be said about a difference at this probability."""
    if probability is None:
        return "not measured"
    if probability < SIGNIFICANCE:
        return "significant"
    if probability < 0.15:
        return "suggestive, not significant"
    return "no difference"
