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

from typing import cast

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


# -- the loop that said it did not count, and counted ----------------------


@pytest.mark.asyncio
async def test_more_rate_limits_than_attempts_still_succeeds() -> None:
    """A 429 must not consume one of the three attempts reserved for bad JSON.

    The first version of this said so in a comment and did the opposite:
    `continue` inside `for attempt in range(MAX_ATTEMPTS)` advances the
    counter, so three consecutive rate limits exhausted the loop and killed a
    full-coverage run at module nine -- twice, because the comment read as
    though the case were handled.
    """
    from pydantic import BaseModel

    from augury.core.adapters.provider import MAX_ATTEMPTS, Pricing, ProviderAdapter

    class Answer(BaseModel):
        value: str

    class _Limited:
        """Rate-limits more times than there are attempts, then answers."""

        def __init__(self, times: int) -> None:
            self.remaining = times
            self.calls = 0

        async def create(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.remaining > 0:
                self.remaining -= 1
                raise RuntimeError("Error code: 429 - rate_limit_exceeded ... try again in 1ms")
            from autogen_core.models import CreateResult, RequestUsage

            return CreateResult(
                content='{"value": "ok"}',
                usage=RequestUsage(prompt_tokens=1, completion_tokens=1),
                cached=False,
                finish_reason="stop",
            )

    client = _Limited(times=MAX_ATTEMPTS + 2)
    adapter = ProviderAdapter(
        client,
        model_id="a-model",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=1.0),
    )

    completion = await adapter.call(prompt="p", schema=Answer)

    assert completion.result.value == "ok"  # type: ignore[attr-defined]
    assert adapter.rate_limited == MAX_ATTEMPTS + 2
    assert adapter.retries == 0, "a rate limit is not a rejected answer"


@pytest.mark.asyncio
async def test_the_wait_budget_is_per_call_not_per_adapter() -> None:
    """One adapter serves a whole review, so a lifetime budget runs out.

    The wait counter lived on the adapter and never reset. Eight waits across
    a 261-module run exhausted it, and every 429 after that was fatal --
    which is why a full-coverage run still died at module eight with the
    retry logic apparently in place.
    """
    from pydantic import BaseModel

    from augury.core.adapters.provider import Pricing, ProviderAdapter

    class Answer(BaseModel):
        value: str

    class _LimitsEveryOtherCall:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls % 2 == 1:
                raise RuntimeError("429 rate_limit_exceeded, try again in 1ms")
            from autogen_core.models import CreateResult, RequestUsage

            return CreateResult(
                content='{"value": "ok"}',
                usage=RequestUsage(prompt_tokens=1, completion_tokens=1),
                cached=False,
                finish_reason="stop",
            )

    adapter = ProviderAdapter(
        _LimitsEveryOtherCall(),
        model_id="a-model",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=1.0),
    )

    # Far more calls than one call's wait budget. Every one must succeed.
    for _ in range(12):
        completion = await adapter.call(prompt="p", schema=Answer)
        answered = cast("Answer", completion.result)
        assert answered.value == "ok"

    assert adapter.rate_limited == 12
