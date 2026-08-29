"""Whether a difference between two arms is a difference.

Eyeballing two means is how the first two claims in this project's changelog
came to be withdrawn. The tests are in the harness so the verdict is produced
by the run rather than argued for afterwards.
"""

import pytest

from augury.evaluation.significance import fisher_exact, permutation_p


def test_a_clear_difference_is_significant() -> None:
    probability = fisher_exact(hits_a=30, tested_a=30, hits_b=0, tested_b=30)

    assert probability is not None
    assert probability < 0.001


def test_a_suggestive_difference_is_not_dressed_up_as_significant() -> None:
    """26 of 37 against 12 of 25 is the real observed comparison. It looks
    like a win and does not reach the threshold."""
    probability = fisher_exact(hits_a=26, tested_a=37, hits_b=12, tested_b=25)

    assert probability == pytest.approx(0.111, abs=0.01)


def test_identical_rates_are_not_a_difference() -> None:
    assert fisher_exact(hits_a=6, tested_a=11, hits_b=6, tested_b=11) == pytest.approx(1.0)


def test_an_empty_arm_yields_no_verdict() -> None:
    assert fisher_exact(hits_a=0, tested_a=0, hits_b=3, tested_b=5) is None


def test_permutation_finds_no_difference_between_similar_samples() -> None:
    """0.850 against 0.800 over eight seeds each is what the arms actually
    produced, and it is nothing."""
    baseline = [1.0, 1.0, 0.8, 1.0, 0.8, 0.8, 0.6, 0.8]
    augury = [0.8] * 8

    assert permutation_p(augury, baseline) > 0.5


def test_permutation_finds_a_real_separation() -> None:
    assert permutation_p([1.0] * 6, [0.2] * 6) < 0.01


def test_permutation_refuses_a_sample_too_small_to_say_anything() -> None:
    """Three against three cannot reach 0.05 whatever the result, so the
    number would be theatre."""
    assert permutation_p([1.0, 1.0, 1.0], [0.2, 0.2, 0.2]) > 0.05
