"""Combining scores across cases is where a comparison is quietly decided.

An adversarial review built two arms where mean-of-ratios and pooled-ratio
crown opposite winners over the same case set, and both readings are defensible
as "Falsifiable Precision across the cases". Leaving the rule unwritten until
the results table is built, at 3am, is how a submission gets an indefensible
headline number.
"""

import pytest

from augury.core.scoring import Score, aggregate


def score(*, falsifiable: int, observations: int, case: str, arm: str = "baseline") -> Score:
    return Score(
        case=case,
        arm=arm,
        seed=0,
        model_id="stub",
        seeded=0,
        found=0,
        total_findings=observations,
        falsifiable=falsifiable,
        tested=0,
        experiments=0,
        hits=0,
        broken=0,
        dropped=0,
        falsifiable_precision=falsifiable / observations if observations else None,
        hit_rate=None,
        prediction_coverage=None,
        usd=0.01,
        seconds=1.0,
    )


def test_rates_are_pooled_over_summed_counts_not_averaged() -> None:
    """Arm A looks better per case and worse in total. 1-of-1 and 1-of-100 is
    not a 0.505 reviewer; it is a 0.0198 reviewer that got lucky on a tiny
    case. Averaging ratios lets the tiny case outvote the large one."""
    arm = aggregate(
        [
            score(falsifiable=1, observations=1, case="a"),
            score(falsifiable=1, observations=100, case="b"),
        ]
    )

    assert arm.falsifiable_precision == pytest.approx(2 / 101)


def test_a_case_that_found_nothing_still_counts_in_the_denominator() -> None:
    """Skipping None-valued cases averages the two arms over different case
    subsets while the table says the cases were identical."""
    arm = aggregate(
        [
            score(falsifiable=1, observations=2, case="a"),
            score(falsifiable=0, observations=0, case="b"),
            score(falsifiable=0, observations=3, case="c"),
        ]
    )

    assert arm.cases == 3
    assert arm.falsifiable_precision == pytest.approx(1 / 5)


def test_the_spread_across_cases_is_reported_beside_the_pooled_rate() -> None:
    """A pooled rate hides whether one case carried the whole result."""
    arm = aggregate(
        [
            score(falsifiable=10, observations=10, case="a"),
            score(falsifiable=0, observations=10, case="b"),
        ]
    )

    assert arm.falsifiable_precision == pytest.approx(0.5)
    assert arm.per_case_low == pytest.approx(0.0)
    assert arm.per_case_high == pytest.approx(1.0)


def test_costs_are_summed_not_averaged() -> None:
    arm = aggregate([score(falsifiable=1, observations=1, case=c) for c in "abc"])

    assert arm.usd == pytest.approx(0.03)


def test_two_arms_cannot_be_aggregated_together() -> None:
    """A row in the results table is one arm. Mixing them silently would make
    the comparison meaningless in a way nobody could see afterwards."""
    with pytest.raises(ValueError, match="arm"):
        aggregate(
            [
                score(falsifiable=1, observations=1, case="a", arm="baseline"),
                score(falsifiable=1, observations=1, case="a", arm="augury"),
            ]
        )


def test_aggregating_nothing_is_refused() -> None:
    """An empty arm has no result, and reporting 0.000 for it would read as
    a measurement."""
    with pytest.raises(ValueError, match="no scores"):
        aggregate([])


# -- the floor under a published rate --------------------------------------
# Measured on B01: the baseline's hit rate rested on four tested predictions
# and one of its seeds produced 1.000 from a single measurement. A ratio over
# one is not a rate, and printing it in a results table beside a ratio over
# fifty invites exactly the wrong comparison.


def measured(*, arm: str, tested: int, hits: int) -> Score:
    return Score(
        case="B01",
        arm=arm,
        seed=0,
        model_id="stub",
        seeded=5,
        found=5,
        total_findings=tested,
        falsifiable=tested,
        tested=tested,
        experiments=tested,
        hits=hits,
        broken=0,
        dropped=0,
        falsifiable_precision=1.0,
        hit_rate=hits / tested if tested else None,
        prediction_coverage=1.0,
        usd=0.01,
        seconds=1.0,
    )


def test_a_hit_rate_over_too_few_measurements_is_withheld() -> None:
    arm = aggregate([measured(arm="a", tested=1, hits=1)])

    assert arm.hit_rate is None
    assert arm.tested == 1
    assert arm.hits == 1


def test_the_counts_are_always_reported_even_when_the_rate_is_not() -> None:
    """Withholding the ratio must not hide the evidence. A reader can still
    see one of one and judge it themselves."""
    arm = aggregate([measured(arm="a", tested=2, hits=0)])

    assert arm.hit_rate is None
    assert (arm.hits, arm.tested) == (0, 2)


def test_a_hit_rate_over_enough_measurements_is_published() -> None:
    arm = aggregate([measured(arm="a", tested=10, hits=5)])

    assert arm.hit_rate == pytest.approx(0.5)


def test_the_floor_is_reached_by_pooling_across_seeds() -> None:
    """Three seeds of four tested predictions each is twelve measurements, and
    twelve is a rate even though four is not."""
    arm = aggregate([measured(arm="a", tested=4, hits=2) for _ in range(3)])

    assert arm.tested == 12
    assert arm.hit_rate == pytest.approx(0.5)
