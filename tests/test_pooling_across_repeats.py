"""Pooling across repeats that are not independent multiplies the evidence.

Under replay every repeat is the same recording, so five repeats produce five
identical Scores. Pooling them gave `25 / 30` where the observation was `5 / 6`,
and `fisher_exact` -- which, unlike `compare` and `recall_permutation_p`, had no
independence guard -- turned p = 1.0000 into the published p = 0.052.

That published number was the only result in the project pointing at the
pipeline, and it was one observation counted five times.
"""

from __future__ import annotations

from augury.core.scoring import Score
from augury.evaluation.sweep import summarise


def _score(arm: str, seed: int, *, hits: int, tested: int, experiments: int) -> Score:
    return Score(
        case="B01",
        arm=arm,
        seed=seed,
        model_id="stub",
        seeded=5,
        found=4,
        total_findings=6,
        observations=6,
        falsifiable=6,
        tested=tested,
        experiments=experiments,
        hits=hits,
        broken=0,
        dropped=0,
        falsifiable_precision=1.0,
        hit_rate=hits / tested if tested else None,
        prediction_coverage=None,
        usd=0.01,
        seconds=1.0,
    )


def _identical(arm: str, repeats: int) -> list[Score]:
    """What replay produces: the same numbers, `repeats` times."""
    return [_score(arm, s, hits=6, tested=6, experiments=5) for s in range(repeats)]


def test_non_independent_repeats_are_counted_once() -> None:
    result = summarise(_identical("augury", 5), independent=False)

    assert (result.hits, result.tested) == (6, 6), (
        f"pooled to {result.hits}/{result.tested}: five copies of one observation"
    )
    assert result.experiments == 5


def test_independent_repeats_still_pool() -> None:
    """Genuine repeats are genuine evidence and must accumulate."""
    result = summarise(_identical("augury", 5), independent=True)

    assert (result.hits, result.tested) == (30, 30)


def test_the_significance_test_is_withheld_when_repeats_are_not_independent() -> None:
    from augury.evaluation.sweep import hit_rate_fisher_p

    left = summarise(_identical("augury", 5), independent=False)
    right = summarise(
        [_score("baseline", s, hits=5, tested=6, experiments=6) for s in range(5)],
        independent=False,
    )
    assert hit_rate_fisher_p(left, right) is None

    live_left = summarise(_identical("augury", 5), independent=True)
    live_right = summarise(
        [_score("baseline", s, hits=5, tested=6, experiments=6) for s in range(5)],
        independent=True,
    )
    assert hit_rate_fisher_p(live_left, live_right) is not None
