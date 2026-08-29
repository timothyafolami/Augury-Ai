"""A review of thirty-nine modules must not die because one call came back empty.

A DeepSeek run ended on its eleventh module: one specialist returned no
content three times running, the exception left `asyncio.gather`, and the
whole review went with it. Every finding produced up to that point was thrown
away with it.

A specialist is one opinion about one concern of one module. Losing it costs
that opinion. It must not cost the other seven specialists on the same module,
the thirty-eight other modules, or the findings already in hand.
"""

from __future__ import annotations

import pytest

from augury.core.drafts import DraftReport


class _Sometimes:
    """A model that fails for one named layer and answers for the rest."""

    def __init__(self, broken: str) -> None:
        self.broken = broken
        self.asked: list[str] = []

    async def structured(self, *, prompt: str, schema: type) -> object:
        name = prompt.split("|", 1)[0]
        self.asked.append(name)
        if name == self.broken:
            raise ValueError("returned an empty response")
        return DraftReport(findings=[])


async def test_a_specialist_that_raises_is_skipped_rather_than_fatal() -> None:
    from augury.agents.augury import gather_survivors

    async def ok() -> DraftReport:
        return DraftReport(findings=[])

    async def broken() -> DraftReport:
        raise ValueError("returned an empty response")

    kept = await gather_survivors([ok(), broken(), ok()])

    assert len(kept) == 2, "the two working specialists must still be heard"


async def test_every_specialist_failing_is_not_an_exception_either() -> None:
    """An empty answer for one module is a module with no findings, not a crash."""
    from augury.agents.augury import gather_survivors

    async def broken() -> DraftReport:
        raise ValueError("returned an empty response")

    assert await gather_survivors([broken(), broken()]) == []


async def test_a_cancellation_is_not_swallowed() -> None:
    """Ctrl-C must still stop the run; only provider faults are absorbed."""
    from augury.agents.augury import gather_survivors

    async def cancelled() -> DraftReport:
        raise asyncio.CancelledError

    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await gather_survivors([cancelled()])


async def test_a_module_that_fails_leaves_a_gap_in_place_not_a_shorter_list() -> None:
    """The batch's cost is apportioned by zipping modules with their results.

    Dropping a failed module would shift every result after it onto the wrong
    module, so a module that could not be read comes back as a module with no
    findings -- which is what it is -- in the position it was asked about.
    """
    from augury.agents.augury import gather_each

    async def ok() -> DraftReport:
        return DraftReport(findings=[])

    async def broken() -> DraftReport:
        raise ValueError("returned an empty response")

    kept = await gather_each([ok(), broken(), ok()], instead=DraftReport(findings=[]))

    assert len(kept) == 3, "one result per module asked about, in order"


async def test_a_module_that_fails_is_still_counted_as_read() -> None:
    """Otherwise the scheduler offers it again and the run cannot end."""
    from augury.agents.augury import gather_each

    async def broken() -> DraftReport:
        raise ValueError("nope")

    kept = await gather_each([broken()], instead=DraftReport(findings=[]))

    assert kept[0].findings == []


async def test_cancellation_still_stops_a_batch() -> None:
    import asyncio

    from augury.agents.augury import gather_each

    async def cancelled() -> DraftReport:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await gather_each([cancelled()], instead=DraftReport(findings=[]))
