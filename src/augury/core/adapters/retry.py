"""Waiting out a rate limit instead of losing the run.

A full-coverage review of a 261-module backend died on its ninth module with a
429. Groq allows 250,000 tokens a minute; eight concurrent modules exceed that,
and the whole review was lost along with everything already paid for.

A 429 says "try again", usually with a number attached. Treating it as fatal
discards a run that would have succeeded a second later -- and the bigger the
repository the more certain that is, so the failure grows with exactly the
codebases this exists for.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# `try again in 786.72ms` / `try again in 2.5s`. The provider knows how long it
# needs; guessing when told is not an improvement.
_DELAY = re.compile(r"try again in\s*([0-9.]+)\s*(ms|s)\b", re.IGNORECASE)

# What a rate limit calls itself, across providers.
_MARKERS = ("429", "rate limit", "rate_limit", "too many requests", "tokens per minute")

# Beyond this a wait is a hang with extra steps.
MAX_DELAY_SECONDS = 30.0


class RateLimited(Exception):
    """The provider asked us to wait."""

    @staticmethod
    def looks_like(message: str) -> bool:
        lowered = message.lower()
        return any(marker in lowered for marker in _MARKERS)


def retry_after(message: str) -> float | None:
    """How long the provider asked for, in seconds, if it said."""
    match = _DELAY.search(message)
    if match is None:
        return None
    value = float(match.group(1))
    return value / 1000.0 if match.group(2).lower() == "ms" else value


def sleep_schedule(*, attempts: int, floor: float = 1.0) -> Iterator[float]:
    """Exponential backoff, bounded, one delay per remaining attempt."""
    delay = floor
    for _ in range(attempts):
        yield min(delay, MAX_DELAY_SECONDS)
        delay *= 2
