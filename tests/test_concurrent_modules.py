"""Reviewing modules concurrently, because coverage is the point.

Full coverage of a real backend is 261 modules. Sequentially that is 56
minutes, and the reason the first run stopped at 42 was a budget set to hide
the wall-clock rather than the cost -- which is $1.87 for the whole thing.

So the scheduler hands out a batch, the batch is reviewed at once, and the
results are recorded together. Batched rather than unbounded: the scheduler
promotes a module whose neighbours produced findings, and that adaptivity needs
results to come back before the next choice is made.
"""

from __future__ import annotations

from augury.core.cartography import ModuleNode, RepoMap, Signal
from augury.core.scheduling import Budget, Scheduler
from augury.core.scheduling.scheduler import ENOUGH_TO_TRUST, PROBE_BATCH


def _repo(count: int) -> RepoMap:
    return RepoMap(
        root="/x",
        modules=[
            ModuleNode(
                path=f"app/m{n}.py",
                loc=40,
                signals=frozenset({Signal.DATA}),
                depth=0,
            )
            for n in range(count)
        ],
    )


def _rate_known(scheduler: Scheduler, repo: RepoMap) -> None:
    """Record enough cheap reads that the scheduler has measured the rate.

    Before that it deliberately hands out small batches, because the estimate
    it starts with is a guess and a guess ten times too cheap spends the whole
    ceiling before the first result comes back.
    """
    for module in repo.modules[:ENOUGH_TO_TRUST]:
        scheduler.record(module, findings=0, spent_usd=0.0001)


def test_a_batch_is_handed_out_whole() -> None:
    repo = _repo(20)
    scheduler = Scheduler(repo, Budget(usd=5.0))
    _rate_known(scheduler, repo)

    batch = scheduler.next_batch(8)

    assert len(batch) == 8
    assert len({m.path for m in batch}) == 8, "a module appeared twice in one batch"


def test_a_batch_never_exceeds_what_is_left() -> None:
    repo = _repo(6)
    scheduler = Scheduler(repo, Budget(usd=5.0))
    _rate_known(scheduler, repo)

    assert len(scheduler.next_batch(8)) == 3, "three of the six are already read"


def test_the_first_batch_is_small_while_the_rate_is_still_a_guess() -> None:
    scheduler = Scheduler(_repo(20), Budget(usd=5.0))

    assert len(scheduler.next_batch(8)) == PROBE_BATCH


def test_an_exhausted_scheduler_returns_an_empty_batch() -> None:
    scheduler = Scheduler(_repo(2), Budget(usd=5.0))
    for module in scheduler.next_batch(8):
        scheduler.record(module, findings=0, spent_usd=0.0)

    assert scheduler.next_batch(8) == []


def test_a_batch_stops_at_the_budget() -> None:
    """The ceiling still binds; it just binds on a batch rather than a module."""
    scheduler = Scheduler(_repo(100), Budget(usd=0.0005))

    batch = scheduler.next_batch(50)

    assert len(batch) < 50


def test_every_module_is_eventually_handed_out() -> None:
    """Coverage is the point: a module must not be lost between batches."""
    scheduler = Scheduler(_repo(37), Budget(usd=5.0))

    seen: set[str] = set()
    while batch := scheduler.next_batch(8):
        for module in batch:
            seen.add(module.path)
            scheduler.record(module, findings=0, spent_usd=0.0)

    assert len(seen) == 37
