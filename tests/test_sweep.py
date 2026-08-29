"""Running an arm more than once, because one run is not a measurement.

A single run of each arm on case B01 gave the baseline 5/5 and then 4/5 at
temperature zero. Reporting either number as the result would have been
reporting noise. A sweep repeats each arm and reports the spread beside the
mean, so a difference smaller than the variance is visibly not a difference.
"""

import pytest

from augury.core.scoring import Score
from augury.evaluation.sweep import SweepResult, summarise


def score(*, arm: str, seed: int, found: int, seeded: int = 5) -> Score:
    return Score(
        case="B01",
        arm=arm,
        seed=seed,
        model_id="stub",
        seeded=seeded,
        found=found,
        total_findings=found,
        falsifiable=found,
        tested=0,
        experiments=0,
        hits=0,
        broken=0,
        dropped=0,
        falsifiable_precision=1.0 if found else None,
        hit_rate=None,
        prediction_coverage=None,
        usd=0.01,
        seconds=1.0,
    )


def test_reports_the_mean_across_seeds() -> None:
    result = summarise([score(arm="a", seed=s, found=f) for s, f in enumerate([5, 4, 3])])

    assert result.recall_mean == pytest.approx(0.8)


def test_reports_the_spread_so_a_single_run_cannot_pass_as_a_result() -> None:
    result = summarise([score(arm="a", seed=s, found=f) for s, f in enumerate([5, 4, 3])])

    assert result.recall_low == pytest.approx(0.6)
    assert result.recall_high == pytest.approx(1.0)


def test_a_difference_inside_the_spread_is_called_inconclusive() -> None:
    """4/5 against 5/5 on one run each is not a finding, and saying so is the
    difference between a result and a claim."""
    steady = summarise([score(arm="a", seed=s, found=4) for s in range(3)])
    noisy = summarise([score(arm="b", seed=s, found=f) for s, f in enumerate([5, 4, 3])])

    assert SweepResult.compare(noisy, steady) == "inconclusive"


def test_a_difference_clear_of_both_spreads_is_called() -> None:
    weak = summarise([score(arm="a", seed=s, found=1) for s in range(3)])
    strong = summarise([score(arm="b", seed=s, found=5) for s in range(3)])

    assert SweepResult.compare(strong, weak) == "better"
    assert SweepResult.compare(weak, strong) == "worse"


def test_one_seed_is_reported_as_unrepeated() -> None:
    """Not an error, but never presented as though it had been repeated."""
    result = summarise([score(arm="a", seed=0, found=4)])

    assert result.seeds == 1
    assert result.repeated is False


def test_mixing_arms_in_one_sweep_is_refused() -> None:
    with pytest.raises(ValueError, match="arm"):
        summarise([score(arm="a", seed=0, found=4), score(arm="b", seed=1, found=4)])


# -- pooling is how a rate reaches its floor --------------------------------
# A single run of B01 yields three or four distinct experiments, under the
# floor of five, so every per-seed hit rate is correctly withheld. Averaging
# withheld values gives nothing. The seeds have to be pooled.


def measured(*, arm: str, seed: int, tested: int, hits: int, experiments: int) -> Score:
    return Score(
        case="B01",
        arm=arm,
        seed=seed,
        model_id="stub",
        seeded=5,
        found=4,
        total_findings=tested,
        falsifiable=tested,
        tested=tested,
        experiments=experiments,
        hits=hits,
        broken=0,
        dropped=0,
        falsifiable_precision=1.0,
        hit_rate=None,
        prediction_coverage=1.0,
        usd=0.01,
        seconds=1.0,
    )


def test_hit_rate_is_pooled_across_seeds_not_averaged() -> None:
    """Three seeds of four experiments is twelve measurements, and twelve is
    a rate even though four is not."""
    result = summarise(
        [measured(arm="a", seed=s, tested=4, hits=3, experiments=4) for s in range(3)]
    )

    assert result.experiments == 12
    assert result.hit_rate == pytest.approx(0.75)


def test_a_sweep_too_small_to_pool_still_withholds_the_rate() -> None:
    result = summarise([measured(arm="a", seed=0, tested=2, hits=2, experiments=2)])

    assert result.hit_rate is None
    assert (result.hits, result.tested) == (2, 2)


def test_the_counts_behind_a_pooled_rate_are_reported() -> None:
    """A rate without its denominator hides how much it rests on."""
    result = summarise(
        [measured(arm="a", seed=s, tested=4, hits=3, experiments=4) for s in range(3)]
    )

    assert (result.hits, result.tested, result.experiments) == (9, 12, 12)
