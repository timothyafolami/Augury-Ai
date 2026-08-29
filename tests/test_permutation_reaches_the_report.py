"""The permutation test must be computed by a command, not just published.

`docs/HOT_TAKE.md` reports "permutation p = 1.00" for recall. `permutation_p`
was defined and unit-tested and called by nothing in `src/`, so no documented
command emitted that number. That is the dead-flag shape one level up: a
statistic in the results that the shipped code does not produce.
"""

from __future__ import annotations

from augury.evaluation.sweep import summarise
from tests.test_sweep import score


def test_a_sweep_keeps_the_per_repeat_recalls_it_summarised() -> None:
    """The permutation test needs the individual runs, not just the range."""
    result = summarise([score(arm="a", seed=s, found=f) for s, f in enumerate([5, 4, 3])])
    assert sorted(result.recalls) == [0.6, 0.8, 1.0]


def test_the_recall_permutation_probability_is_reported() -> None:
    from augury.evaluation.significance import permutation_p

    left = summarise([score(arm="a", seed=s, found=5) for s in range(3)])
    right = summarise([score(arm="b", seed=s, found=1) for s in range(3)])

    assert permutation_p(list(left.recalls), list(right.recalls)) is not None


def test_the_permutation_test_is_withheld_when_repeats_are_not_independent() -> None:
    """Replay makes the permutation test look extremely significant.

    Five copies of 0.800 against five copies of 0.700 permute to p = 0.0079 --
    a confident difference computed from one observation per arm. The same
    non-independence that disqualifies the range disqualifies this, and it is
    more dangerous because it arrives wearing a p-value.
    """
    from augury.evaluation.sweep import recall_permutation_p

    left = summarise([score(arm="a", seed=s, found=4) for s in range(5)], independent=False)
    right = summarise([score(arm="b", seed=s, found=3) for s in range(5)], independent=False)
    assert recall_permutation_p(left, right) is None

    live_left = summarise([score(arm="a", seed=s, found=4) for s in range(5)])
    live_right = summarise([score(arm="b", seed=s, found=3) for s in range(5)])
    assert recall_permutation_p(live_left, live_right) is not None
