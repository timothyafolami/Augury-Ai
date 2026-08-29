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
    from augury.agents.augury import Reading, gather_each

    async def ok() -> Reading:
        return Reading.of(DraftReport(findings=[]))

    async def broken() -> Reading:
        raise ValueError("returned an empty response")

    kept = await gather_each([ok(), broken(), ok()], instead=Reading.unread("x", "gone"))

    assert len(kept) == 3, "one result per module asked about, in order"


async def test_a_module_that_fails_is_still_counted_as_read() -> None:
    """Otherwise the scheduler offers it again and the run cannot end."""
    from augury.agents.augury import Reading, gather_each

    async def broken() -> Reading:
        raise ValueError("nope")

    kept = await gather_each([broken()], instead=Reading.unread("x", "gone"))

    assert kept[0].report.findings == []
    assert not kept[0].read, "a module that raised was not read"


async def test_cancellation_still_stops_a_batch() -> None:
    import asyncio

    from augury.agents.augury import Reading, gather_each

    async def cancelled() -> Reading:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await gather_each([cancelled()], instead=Reading.unread("x", "gone"))


async def test_a_module_no_specialist_could_read_is_not_reported_as_clean() -> None:
    """Absorbing the failure must not turn it into a clean bill of health.

    When every specialist on a module fails, the module produced no findings
    for the same reason an unread file produces none -- nobody looked. Reported
    as analysed, the coverage line claims a module was reviewed that was not,
    and the worse the provider behaves the cleaner the report looks.
    """
    from augury.agents.augury import Reading

    unread = Reading.unread("app.py", "every specialist failed")

    assert not unread.read
    assert unread.report.findings == []
    assert "specialist" in unread.why


def test_a_module_that_was_read_says_so() -> None:
    from augury.agents.augury import Reading

    read = Reading.of(DraftReport(findings=[]))

    assert read.read
    assert read.why == ""
