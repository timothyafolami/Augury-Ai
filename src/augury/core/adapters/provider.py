"""One adapter over every provider, and the factory that builds it.

Groq, OpenAI and Anthropic differ in base URL, model name and price. None of
those differences belongs in an agent, so they are resolved here and the rest
of the system sees only `ChatModel`.
"""

from __future__ import annotations

from typing import TypeVar

from autogen_core.models import ChatCompletionClient, ModelFamily, ModelInfo, UserMessage
from pydantic import BaseModel

from augury.core.adapters.base import ChatModel, ModelSpec, Usage
from augury.core.adapters.pricing import Pricing, pricing_for

T = TypeVar("T", bound=BaseModel)

# Groq is OpenAI-compatible, so it is a base URL rather than a third client.
OPENAI_COMPATIBLE_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "groq": "https://api.groq.com/openai/v1",
}


class ProviderAdapter:
    """Turns a provider response into a validated object and a measured cost."""

    def __init__(self, client: ChatCompletionClient, *, model_id: str, pricing: Pricing) -> None:
        self._client = client
        self._model_id = model_id
        self._pricing = pricing
        self._usage = Usage()

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def usage(self) -> Usage:
        """Cumulative for the life of this adapter, matching provider SDKs."""
        return self._usage

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        """Ask for the schema, not for JSON in prose, and validate the answer.

        A response that does not match is raised rather than repaired: a
        half-populated finding flowing downstream is worse than a loud failure.
        """
        response = await self._client.create(
            messages=[UserMessage(content=prompt, source="augury")],
            json_output=schema,
        )
        self._record(response.usage)

        content = response.content
        if not isinstance(content, str):
            raise TypeError(f"expected text from {self._model_id}, got {type(content).__name__}")
        return schema.model_validate_json(content)

    def _record(self, usage: object) -> None:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        self._usage = self._usage + Usage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            usd=self._pricing.cost(
                input_tokens=prompt_tokens, output_tokens=completion_tokens
            ),
        )


def build_model(spec: ModelSpec, *, api_key: str) -> ChatModel:
    """Resolve a declarative spec into a live adapter.

    Pricing is looked up first so an unpriced model fails here, before a run
    starts, rather than reporting itself as free at the end of one.
    """
    pricing = pricing_for(spec.model)

    if spec.provider in OPENAI_COMPATIBLE_BASE_URLS:
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        base_url = OPENAI_COMPATIBLE_BASE_URLS[spec.provider]
        client: ChatCompletionClient = OpenAIChatCompletionClient(
            model=spec.model,
            api_key=api_key,
            temperature=spec.temperature,
            model_info=MODEL_CAPABILITIES,
            **({"base_url": base_url} if base_url else {}),
        )
    else:
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient

        client = AnthropicChatCompletionClient(
            model=spec.model,
            api_key=api_key,
            temperature=spec.temperature,
            model_info=MODEL_CAPABILITIES,
        )

    return ProviderAdapter(client, model_id=spec.model, pricing=pricing)


# Declared rather than looked up. Groq's models have no entry in autogen's
# registry at all, and every model this project uses is driven the same way:
# text in, structured output back, no vision. Stating it keeps a new model from
# being refused for want of a registry entry.
MODEL_CAPABILITIES: ModelInfo = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": True,
    "family": ModelFamily.UNKNOWN,
    "multiple_system_messages": True,
}
