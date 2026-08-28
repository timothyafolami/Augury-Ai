"""The one interface every model provider is reached through.

Nothing in the agent mesh imports a provider SDK. Agents depend on `ChatModel`,
the runtime picks an implementation from config, and swapping Anthropic for
OpenAI for the robustness run is a config change rather than a code change.
"""

from __future__ import annotations

from typing import Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class Usage(BaseModel):
    """Spend accounting. Reported cost is measured here, never estimated."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            usd=self.usd + other.usd,
        )

    def __radd__(self, other: int | Usage) -> Usage:
        """Lets `sum(...)` aggregate spend across a mesh of agents.

        `sum` starts from the integer 0, which is the only int this accepts.
        """
        if isinstance(other, Usage):
            return self.__add__(other)
        if other == 0:
            return self
        return NotImplemented

    def __sub__(self, other: Usage) -> Usage:
        """The delta between two readings of a cumulative counter."""
        return Usage(
            input_tokens=self.input_tokens - other.input_tokens,
            output_tokens=self.output_tokens - other.output_tokens,
            usd=self.usd - other.usd,
        )


@runtime_checkable
class ChatModel(Protocol):
    """A model that returns a validated pydantic object, never loose text.

    `usage` is **cumulative** for the life of the client, matching how provider
    SDKs report it. A caller that wants the cost of one call takes the delta.
    """

    @property
    def model_id(self) -> str: ...

    async def structured(self, *, prompt: str, schema: type[T]) -> T: ...

    @property
    def usage(self) -> Usage: ...


Provider = Literal["anthropic", "openai", "groq"]


class ModelSpec(BaseModel):
    """Declarative model selection, resolved at runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
