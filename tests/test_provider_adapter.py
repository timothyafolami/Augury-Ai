"""Every provider is reached through one adapter.

Groq, OpenAI and Anthropic differ in base URL, model name and price, not in
anything an agent should know about. These tests pin that the adapter turns a
provider response into a validated object and a truthful cost, using a stand-in
client so no test ever needs a key.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from autogen_core.models import CreateResult, RequestUsage
from pydantic import BaseModel, ValidationError

from augury.core.adapters.base import ChatModel, ModelSpec, Provider
from augury.core.adapters.provider import Pricing, ProviderAdapter, build_model


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

    async def create(self, messages: Any, **kwargs: Any) -> CreateResult:
        self.calls += 1
        self.last_kwargs = kwargs
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
    model = build_model(
        ModelSpec(provider="groq", model="llama-3.3-70b-versatile"), api_key="test-key"
    )

    assert model.model_id == "llama-3.3-70b-versatile"


@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq"])
def test_every_declared_provider_can_be_built(provider: Provider) -> None:
    model = build_model(ModelSpec(provider=provider, model="a-model"), api_key="test-key")

    assert isinstance(model, ChatModel)


def test_an_unpriced_model_is_refused_rather_than_reported_as_free() -> None:
    """A missing price silently becomes $0.00 per review, which is a false
    number in a submission whose whole claim is measured cost."""
    with pytest.raises(KeyError, match="pricing"):
        build_model(ModelSpec(provider="openai", model="not-a-real-model"), api_key="k")
