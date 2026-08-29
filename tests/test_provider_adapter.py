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
    last_kwargs: dict[str, Any] | None = None
    prompts: list[str] = field(default_factory=list)

    async def create(self, messages: Any, **kwargs: Any) -> CreateResult:
        self.calls += 1
        self.last_kwargs = kwargs
        self.prompts.append(str(getattr(messages[0], "content", messages)))
        return CreateResult(
            finish_reason="stop",
            content=self.payload,
            usage=RequestUsage(
                prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens
            ),
            cached=False,
        )


def adapter(payload: str, **kwargs: Any) -> ProviderAdapter:
    return ProviderAdapter(
        StubClient(payload=payload, **kwargs),
        model_id="stub/model-1",
        pricing=Pricing(usd_per_1m_input=1.0, usd_per_1m_output=3.0),
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
    """Asking for JSON in the prompt and hoping is not structured output."""
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
