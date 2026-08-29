"""Buffering inbound events until a worker can take them."""

import asyncio
from typing import Any

# Unbounded so a burst is never rejected: the courier retries anything we
# refuse, and a retry costs more than holding the event for a moment.
_pending: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


async def accept(event: dict[str, Any]) -> None:
    """Take an event from the courier."""
    await _pending.put(event)


async def take() -> dict[str, Any]:
    """The next event for a worker."""
    return await _pending.get()


def depth() -> int:
    """How many events are waiting."""
    return _pending.qsize()
