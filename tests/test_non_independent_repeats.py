"""Repeats that are not independent cannot separate two arms.

`make eval-replay` prints recall ranges of 0.700-0.700 and 0.800-0.800. They do
not overlap, so `compare` called it "better" -- the pipeline beating the
baseline on recall, published from a single observation per arm.

The mistake is subtler than "zero width is suspicious". Three live runs that all
return 1/5 against three that all return 5/5 also have zero width, and that is
real evidence which must survive. What disqualifies replay is that its repeats
are one recording served five times: the arm was observed once, however many
times it was asked. So the guard is on independence, which the harness knows,
rather than on the shape of the numbers, which cannot tell the two apart.
"""

from __future__ import annotations

from augury.evaluation.sweep import SweepResult


def _result(low: float, high: float, *, seeds: int = 5, independent: bool = True) -> SweepResult:
    return SweepResult(
        arm="x",
        seeds=seeds,
        independent=independent,
        recall_mean=(low + high) / 2,
        recall_low=low,
        recall_high=high,
        hits=0,
        tested=0,
        experiments=0,
        precision_mean=None,
        hit_rate=None,
        failed=0,
        usd_mean=0.0,
        seconds_mean=0.0,
    )


def test_replayed_repeats_cannot_win() -> None:
    """The exact numbers and shape make eval-replay produces."""
    augury = _result(0.800, 0.800, independent=False)
    baseline = _result(0.700, 0.700, independent=False)
    assert SweepResult.compare(augury, baseline) == "inconclusive"


def test_replayed_repeats_cannot_lose_either() -> None:
    left = _result(0.700, 0.700, independent=False)
    right = _result(0.800, 0.800, independent=False)
    assert SweepResult.compare(left, right) == "inconclusive"


def test_one_non_independent_arm_disqualifies_the_comparison() -> None:
    left = _result(0.900, 0.900, independent=False)
    assert SweepResult.compare(left, _result(0.500, 0.600)) == "inconclusive"


def test_zero_width_from_independent_repeats_still_counts() -> None:
    """The case the first version of this guard wrongly threw away.

    Three live runs each returning the same number is agreement between three
    observations, not one observation repeated.
    """
    assert SweepResult.compare(_result(0.900, 0.900), _result(0.500, 0.500)) == "better"


def test_separated_ranges_that_both_have_width_still_report_a_winner() -> None:
    # The guard must not disable the comparison it was added to protect.
    assert SweepResult.compare(_result(0.800, 0.900), _result(0.500, 0.600)) == "better"
    assert SweepResult.compare(_result(0.500, 0.600), _result(0.800, 0.900)) == "worse"


def test_overlapping_ranges_remain_inconclusive() -> None:
    assert SweepResult.compare(_result(0.700, 0.900), _result(0.600, 0.800)) == "inconclusive"


def test_recording_collapses_repeats_exactly_as_replay_does() -> None:
    """Recording is the other half of the same defect, and it was missed.

    Under AUGURY_RECORD the first repeat calls the provider and writes a
    cassette; repeats two through five hit that cassette. So recording is
    non-independent for the same reason replay is, and a record run printed
    "ranges clear: better" and "permutation p = 0.0079" while the guard --
    keyed only on replay_only -- let it through.
    """
    from augury.core.adapters.base import ModelSpec
    from augury.core.settings import Settings

    for record, replay in ((True, False), (False, True), (True, True)):
        settings = Settings(
            spec=ModelSpec(provider="groq", model="openai/gpt-oss-120b"),
            api_key="k",
            replay_only=replay,
            record=record,
        )
        assert not settings.repeats_are_independent, (record, replay)

    live = Settings(
        spec=ModelSpec(provider="groq", model="openai/gpt-oss-120b"),
        api_key="k",
        replay_only=False,
        record=False,
    )
    assert live.repeats_are_independent
