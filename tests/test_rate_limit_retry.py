"""A rate limit is a wait, not a failure.

A full-coverage run of a 261-module backend died on its ninth module with a
429: Groq allows 250,000 tokens a minute and eight concurrent modules exceed
it. The whole review was lost, along with everything already paid for.

A 429 says "try again", usually with a number attached. Treating it as fatal
throws away a run that would have succeeded a second later, and the larger the
repository the more certain that is to happen -- so the failure grows with
exactly the codebases this exists for.
"""

from __future__ import annotations

import pytest

from augury.core.adapters.retry import RateLimited, retry_after, sleep_schedule


def test_a_provider_message_naming_a_delay_is_honoured() -> None:
    """Groq says how long to wait. Guessing when told is not better."""
    message = (
        "Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` ... "
        "Please try again in 786.72ms."
    )

    assert retry_after(message) == pytest.approx(0.78672, abs=1e-4)


def test_a_delay_in_seconds_is_read_too() -> None:
    assert retry_after("Please try again in 2.5s") == pytest.approx(2.5)


def test_a_message_with_no_delay_falls_back_to_none() -> None:
    assert retry_after("Error code: 429 - too many requests") is None


def test_the_schedule_backs_off_and_is_bounded() -> None:
    delays = list(sleep_schedule(attempts=5, floor=0.5))

    assert delays[0] == pytest.approx(0.5)
    assert delays == sorted(delays), "a backoff that does not increase is not a backoff"
    assert max(delays) <= 30.0, "an unbounded backoff is a hang with extra steps"


def test_a_rate_limit_is_recognised_from_its_message() -> None:
    assert RateLimited.looks_like("Error code: 429 - rate_limit_exceeded")
    assert RateLimited.looks_like("RateLimitError: tokens per minute (TPM)")
    assert not RateLimited.looks_like("Error code: 400 - invalid request")
    assert not RateLimited.looks_like("Connection reset by peer")


def test_a_429_that_never_clears_eventually_raises() -> None:
    """Retrying forever is a hang. The run should end saying why."""
    assert len(list(sleep_schedule(attempts=3, floor=0.1))) == 3
