"""Every provider is reached through one adapter.

Groq, OpenAI and Anthropic differ in base URL, model name and price, not in
anything an agent should know about. These tests pin that the adapter turns a
provider response into a validated object and a truthful cost, using a stand-in
client so no test ever needs a key.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from autogen_core.models import CreateResult, RequestUsage
from pydantic import BaseModel, ValidationError

from augury.core.adapters.base import ChatModel, ModelSpec, Provider
from augury.core.adapters.provider import (
    MAX_ATTEMPTS,
    Pricing,
    ProviderAdapter,
    build_model,
)


class Finding(BaseModel):
    claim: str
    confidence: float


@dataclass
class StubClient:
    """Stands in for an autogen ChatCompletionClient."""

    payload: str
    prompt_tokens: int = 1000
    completion_tokens: int = 500
    calls: int = 0
    finish_reason: str = "stop"
    raise_first: Exception | None = None
    last_kwargs: dict[str, Any] | None = None
    every: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    async def create(self, messages: Any, **kwargs: Any) -> CreateResult:
        self.calls += 1
        if self.raise_first is not None:
            # Raised before anything is billed, which is the path that exposed
            # a call reporting the previous call's cost.
            failure, self.raise_first = self.raise_first, None
            raise failure
        self.last_kwargs = kwargs
        self.every.append(kwargs)
        self.prompts.append(str(getattr(messages[0], "content", messages)))
        return CreateResult(
            finish_reason=self.finish_reason,  # type: ignore[arg-type]
            content=self.payload,
            usage=RequestUsage(
                prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens
            ),
            cached=False,
        )


def adapter(
    payload: str, *, provider: str = "groq", max_tokens: int = 0, **kwargs: Any
) -> ProviderAdapter:
    """A provider with strict decoding unless a test asks for another.

    The default matters: whether the schema is sent to the provider or written
    into the prompt depends on which provider it is, so an adapter built
    without one exercises neither path deliberately.
    """
    return ProviderAdapter(
        StubClient(payload=payload, **kwargs),
        model_id="stub/model-1",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=3.0),
        provider=provider,
        max_tokens=max_tokens,
    )


async def test_returns_a_validated_object_not_text() -> None:
    model = adapter('{"claim": "p99 crosses 1s at 250rps", "confidence": 0.8}')

    result = await model.structured(prompt="review this", schema=Finding)

    assert result.claim == "p99 crosses 1s at 250rps"
    assert result.confidence == 0.8


async def test_a_response_that_does_not_match_the_schema_is_rejected() -> None:
    """Better a loud failure than a half-populated finding flowing downstream."""
    model = adapter('{"claim": "something"}')

    with pytest.raises(ValidationError):
        await model.structured(prompt="review this", schema=Finding)


async def test_cost_is_computed_from_the_provider_token_counts() -> None:
    """1000 in at $1/M plus 500 out at $3/M is $0.0025. Reported cost is
    measured, never estimated."""
    model = adapter('{"claim": "c", "confidence": 0.1}')

    await model.structured(prompt="review this", schema=Finding)

    assert model.usage.input_tokens == 1000
    assert model.usage.output_tokens == 500
    assert model.usage.usd == pytest.approx(0.0025)


async def test_usage_accumulates_across_calls() -> None:
    model = adapter('{"claim": "c", "confidence": 0.1}')

    await model.structured(prompt="one", schema=Finding)
    await model.structured(prompt="two", schema=Finding)

    assert model.usage.input_tokens == 2000
    assert model.usage.usd == pytest.approx(0.005)


async def test_the_response_schema_is_sent_to_the_provider() -> None:
    """Asking for JSON in the prompt and hoping is not structured output.

    True of every provider that accepts a schema-shaped response_format.
    DeepSeek does not, and is covered by the test below.
    """
    model = adapter('{"claim": "c", "confidence": 0.1}')

    await model.structured(prompt="review this", schema=Finding)

    assert model._client.last_kwargs is not None  # type: ignore[attr-defined]
    assert model._client.last_kwargs["json_output"] is Finding  # type: ignore[attr-defined]


def test_the_adapter_satisfies_the_chat_model_protocol() -> None:
    model: ChatModel = adapter('{"claim": "c", "confidence": 0.1}')

    assert model.model_id == "stub/model-1"


# -- provider selection ----------------------------------------------------


def test_groq_is_reached_through_the_openai_compatible_path() -> None:
    """Groq speaks the OpenAI API, so it is a base URL and a price table
    rather than a third client implementation."""
    model = build_model(ModelSpec(provider="groq", model="openai/gpt-oss-120b"), api_key="test-key")

    assert model.model_id == "openai/gpt-oss-120b"


@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq"])
def test_every_declared_provider_can_be_built(provider: Provider) -> None:
    model = build_model(ModelSpec(provider=provider, model="a-model"), api_key="test-key")

    assert isinstance(model, ChatModel)


def test_an_unpriced_model_is_refused_rather_than_reported_as_free() -> None:
    """A missing price silently becomes $0.00 per review, which is a false
    number in a submission whose whole claim is measured cost."""
    with pytest.raises(KeyError, match="pricing"):
        build_model(ModelSpec(provider="openai", model="not-a-real-model"), api_key="k")


# -- transient invalid output ---------------------------------------------
# A model asked for structured output sometimes returns the schema instead of
# an instance, or JSON the provider rejects. Losing a whole case to that is a
# harness failure, not a reviewer failure, and it would show up as a zero.


class FlakyClient(StubClient):
    """Fails a set number of times before answering."""

    def __init__(self, failures: int, payload: str) -> None:
        super().__init__(payload=payload)
        self.remaining = failures

    async def create(self, messages: Any, **kwargs: Any) -> CreateResult:
        if self.remaining > 0:
            self.remaining -= 1
            self.calls += 1
            self.prompts.append(str(getattr(messages[0], "content", messages)))
            raise RuntimeError("Generated JSON does not match the expected schema")
        return await super().create(messages, **kwargs)


def flaky(failures: int) -> ProviderAdapter:
    return ProviderAdapter(
        FlakyClient(failures, '{"claim": "c", "confidence": 0.1}'),
        model_id="stub/model-1",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=3.0),
    )


async def test_a_rejected_response_is_retried() -> None:
    model = flaky(failures=1)

    result = await model.structured(prompt="review", schema=Finding)

    assert result.claim == "c"


async def test_retries_are_bounded_and_the_last_error_is_raised() -> None:
    """A model that cannot produce the schema will not start doing so, and
    spending the budget discovering that helps nobody."""
    model = flaky(failures=99)

    with pytest.raises(RuntimeError, match="does not match"):
        await model.structured(prompt="review", schema=Finding)

    assert model._client.calls == MAX_ATTEMPTS  # type: ignore[attr-defined]


async def test_a_retry_says_what_went_wrong_so_the_model_can_correct() -> None:
    """Repeating an identical prompt to a deterministic model repeats the
    identical failure. The retry has to differ."""
    model = flaky(failures=1)

    await model.structured(prompt="review this file", schema=Finding)

    first, second = model._client.prompts  # type: ignore[attr-defined]
    assert first != second
    assert "schema" in second.lower()


async def test_retries_are_counted_so_flakiness_is_visible() -> None:
    model = flaky(failures=2)

    await model.structured(prompt="review", schema=Finding)

    assert model.retries == 2


# -- per-call accounting ---------------------------------------------------
# `usage` is cumulative for the life of the client, so a caller that brackets
# a call with before/after gets the wrong answer whenever calls run
# concurrently: every sibling that finished first is inside the delta. Measured
# in a committed trajectory, three gathered specialists recorded 1x, 2x and 3x
# the cost of one call.


async def test_a_call_reports_its_own_usage() -> None:
    model = adapter('{"claim": "c", "confidence": 0.1}')

    completion = await model.call(prompt="review", schema=Finding)

    assert completion.usage.usd == pytest.approx(0.0025)
    assert isinstance(completion.result, Finding)
    assert completion.result.claim == "c"


async def test_concurrent_calls_are_each_charged_only_their_own_cost() -> None:
    """Three gathered calls costing X each must record X, not X, 2X, 3X."""
    import asyncio

    model = adapter('{"claim": "c", "confidence": 0.1}')

    completions = await asyncio.gather(
        *(model.call(prompt=f"review {index}", schema=Finding) for index in range(3))
    )

    assert [c.usage.usd for c in completions] == pytest.approx([0.0025] * 3)
    assert sum(c.usage.usd for c in completions) == pytest.approx(model.usage.usd)


async def test_a_call_reports_its_own_retry_count() -> None:
    """The adapter's lifetime counter says every later call retried once any
    call ever did."""
    model = flaky(failures=1)

    first = await model.call(prompt="one", schema=Finding)
    second = await model.call(prompt="two", schema=Finding)

    assert first.retries == 1
    assert second.retries == 0, "a clean call must not inherit an earlier failure"


async def test_exhausting_every_attempt_reports_the_retries_that_happened() -> None:
    """Three attempts is two retries. Reporting three implies a fourth call
    that was never made."""
    model = flaky(failures=99)

    with pytest.raises(RuntimeError):
        await model.call(prompt="review", schema=Finding)

    assert model.retries == MAX_ATTEMPTS - 1


async def test_a_provider_without_strict_decoding_gets_the_schema_in_the_prompt() -> None:
    """DeepSeek answers 400 to a named schema, so it is shown one instead.

    The requirement is unchanged -- the model must be told the exact shape --
    and only the channel differs, so this asserts the shape arrives rather
    than that a particular flag was set.
    """
    model = adapter('{"claim": "c", "confidence": 0.1}', provider="deepseek")

    await model.structured(prompt="review this", schema=Finding)

    sent = model._client.last_kwargs  # type: ignore[attr-defined]
    assert sent["json_output"] is True, "a named schema would be refused with a 400"
    asked = model._client.prompts[0]  # type: ignore[attr-defined]
    assert "review this" in asked
    assert "confidence" in asked, "the field names have to reach the model somehow"


async def test_a_call_that_fails_before_billing_is_not_charged_the_last_one_s_cost() -> None:
    """`_last_attempt_cost` lives on the adapter, and one adapter serves a review.

    When `create` raises before anything is recorded -- a reset connection, a
    5xx, a 400 -- the retry loop still added `_last_attempt_cost`, which held
    whatever the previous *successful* call was billed. A cheap call following
    an expensive one reported the expensive one's price on top of its own.

    This is the same class of mis-attribution `_record`'s docstring warns
    about, reintroduced through a second piece of shared mutable state.
    """
    expensive = adapter(
        '{"claim": "c", "confidence": 0.1}', prompt_tokens=100_000, completion_tokens=16_000
    )
    await expensive.structured(prompt="a big one", schema=Finding)

    cheap = StubClient(payload='{"claim": "c", "confidence": 0.1}')
    cheap.prompt_tokens = 10
    cheap.completion_tokens = 10
    thrifty = ProviderAdapter(
        cheap,
        model_id="stub/model-1",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=3.0),
        provider="groq",
    )
    # Borrow the expensive adapter's leftover, the way one adapter would.
    thrifty._last_attempt_cost = expensive._last_attempt_cost
    cheap.raise_first = ConnectionError("reset by peer")

    completion = await thrifty.call(prompt="a small one", schema=Finding)

    assert completion.usage.usd < 0.001, (
        f"a call billed for 20 tokens reported ${completion.usage.usd:.6f}"
    )


def test_an_adapter_built_without_a_ceiling_uses_the_same_default_as_the_spec() -> None:
    """Two defaults for one quantity, one of which the other forbids.

    ModelSpec.max_tokens is `default=16_000, gt=0`; the adapter's was 0. With
    0, `_more_room(0)` returns 2 -- so the remedy for running out of room asks
    for a two-token budget, which is guaranteed to run out of room.
    """
    from augury.core.adapters.base import ModelSpec
    from augury.core.adapters.provider import DEFAULT_MAX_TOKENS

    declared = ModelSpec(provider="groq", model="m").max_tokens
    assert declared == DEFAULT_MAX_TOKENS

    built = ProviderAdapter(
        StubClient(payload="{}"),
        model_id="stub/model-1",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=3.0),
    )

    assert built._max_tokens == DEFAULT_MAX_TOKENS


def test_the_raised_ceiling_never_exceeds_what_the_provider_allows() -> None:
    """64K is DeepSeek's headroom, not everyone's.

    Applied to a provider with a lower completion limit, the third attempt
    turns a recoverable truncation into a hard 400 -- whose message will not
    look like running out of room, so the next correction is about the wrong
    thing entirely.
    """
    from augury.core.adapters.provider import most_tokens_for

    assert most_tokens_for("deepseek") > most_tokens_for("groq")
    assert most_tokens_for("anthropic") <= 64_000
    assert most_tokens_for("something-new") <= 64_000
