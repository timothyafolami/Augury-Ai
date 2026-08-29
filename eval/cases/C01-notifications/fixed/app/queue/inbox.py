"""Buffering inbound events until a worker can take them."""

import asyncio
from typing import Any

# Bounded. An unbounded queue does not prevent overload, it hides it: nothing
# fails, and memory and latency climb until something less forgiving gives way.
# Refusing an event tells the courier to slow down, which is information it can
# act on and a growing backlog is not.
MAX_PENDING = 32

_pending: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=MAX_PENDING)


class Overloaded(Exception):
    """The inbox is full. The caller should retry later."""


async def accept(event: dict[str, Any]) -> None:
    """Take an event from the courier, or refuse it."""
    try:
        _pending.put_nowait(event)
    except asyncio.QueueFull as full:
        raise Overloaded("inbox is full") from full


async def take() -> dict[str, Any]:
    """The next event for a worker."""
    return await _pending.get()


def depth() -> int:
    """How many events are waiting."""
    return _pending.qsize()
