"""A ceiling enforced against a guess is enforced against a guess.

A DeepSeek review asked for $0.15 and spent $0.80. The scheduler is not
careless -- it charges an estimate before issuing a module and corrects it
afterwards -- but the estimate is a fixed $0.02 per 1000 lines, and a
reasoning model that spends most of its output budget thinking cost roughly
ten times that. Ten times too cheap an estimate is ten times too many modules
issued before the spend catches up.

The rate is knowable: after a few modules the review has measured it. Nothing
was doing anything with those measurements.
"""

from __future__ import annotations

from augury.core.cartography import ModuleNode, RepoMap
from augury.core.cartography.model import Signal
from augury.core.scheduling.scheduler import (
    ENOUGH_TO_TRUST,
    PROBE_BATCH,
    Budget,
    Scheduler,
)


def _module(path: str, loc: int = 1000) -> ModuleNode:
    return ModuleNode(path=path, loc=loc, fan_in=1, churn=1, signals=frozenset({Signal.NETWORK}))


def _repo(count: int) -> RepoMap:
    return RepoMap(
        root="/tmp/x",
        modules=[_module(f"m{i}.py") for i in range(count)],
        unreachable=(),
        unparsed=[],
    )


def _scheduler(count: int = 40, usd: float = 0.15) -> Scheduler:
    return Scheduler(_repo(count), Budget(usd=usd, usd_per_1k_loc=0.02))


def test_the_estimate_starts_at_the_configured_rate() -> None:
    """With nothing measured there is nothing better to go on."""
    scheduler = _scheduler()
    assert scheduler.expected_usd(_module("x.py", loc=1000)) == 0.02


def test_a_module_that_cost_ten_times_the_estimate_raises_the_estimate() -> None:
    scheduler = _scheduler()
    for index in range(3):
        scheduler.record(_module(f"m{index}.py"), findings=1, spent_usd=0.20)

    assert scheduler.expected_usd(_module("x.py", loc=1000)) > 0.10


def test_a_cheaper_run_than_configured_does_not_lower_the_guard() -> None:
    """Underestimating is what overspends; overestimating only reads less."""
    scheduler = _scheduler()
    for index in range(3):
        scheduler.record(_module(f"m{index}.py"), findings=1, spent_usd=0.001)

    assert scheduler.expected_usd(_module("x.py", loc=1000)) >= 0.02


def test_one_expensive_module_does_not_by_itself_rewrite_the_rate() -> None:
    """A single outlier is noise; the correction should need agreement."""
    scheduler = _scheduler()
    scheduler.record(_module("m0.py"), findings=1, spent_usd=5.0)

    assert scheduler.expected_usd(_module("x.py", loc=1000)) < 1.0


def test_a_run_against_an_expensive_model_stops_near_its_ceiling() -> None:
    """The behaviour all of the above exists for.

    Every module costs ten times the configured estimate. The run must stop
    somewhere near the ceiling rather than five times past it.
    """
    scheduler = _scheduler(count=40, usd=0.15)
    spent = 0.0
    while True:
        batch = scheduler.next_batch(4)
        if not batch:
            break
        for module in batch:
            spent += 0.05
            scheduler.record(module, findings=1, spent_usd=0.05)

    assert spent <= 0.15 * 2, f"asked for $0.15 and spent ${spent:.2f}"


def test_the_first_batch_is_small_enough_to_measure_the_rate_before_committing() -> None:
    """Learning the rate is worth nothing if the money is gone by then.

    The whole $0.82 of an overspending run was one batch of eight modules,
    issued together at the guessed rate and recorded only afterwards. The
    correction had no batch left to apply to.
    """
    scheduler = _scheduler(count=40, usd=5.0)

    assert len(scheduler.next_batch(8)) <= PROBE_BATCH


def test_batches_return_to_full_size_once_the_rate_is_known() -> None:
    """The small batch is a measurement, not a speed limit for the whole run."""
    scheduler = _scheduler(count=40, usd=5.0)
    for index in range(ENOUGH_TO_TRUST):
        scheduler.record(_module(f"m{index}.py"), findings=1, spent_usd=0.001)

    assert len(scheduler.next_batch(8)) == 8


def test_an_expensive_model_now_stops_inside_its_ceiling() -> None:
    """The end-to-end behaviour: measure on a small batch, then respect it."""
    scheduler = _scheduler(count=40, usd=0.15)
    spent = 0.0
    while True:
        batch = scheduler.next_batch(8)
        if not batch:
            break
        for module in batch:
            spent += 0.05
            scheduler.record(module, findings=1, spent_usd=0.05)

    assert spent <= 0.15 * 1.5, f"asked for $0.15 and spent ${spent:.2f}"
