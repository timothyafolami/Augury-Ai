"""What a token costs, per model.

Cost is reported as a measured number, so it has to come from somewhere real.
A model with no entry here is refused at construction rather than silently
reported as free: a false $0.00 in a submission whose claim is measured cost is
worse than a crash.

Rates are USD per million tokens, current as of August 2026. Update alongside
provider price changes; the value is recorded in each run's report so an old
run stays interpretable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Pricing(BaseModel):
    """Token rates for one model."""

    model_config = ConfigDict(frozen=True)

    usd_per_1m_input: float = Field(ge=0)
    usd_per_1m_output: float = Field(ge=0)

    def cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.usd_per_1m_input + output_tokens * self.usd_per_1m_output
        ) / 1_000_000


PRICING: dict[str, Pricing] = {
    # Groq: fast and cheap, which is what makes a full evaluation sweep affordable.
    "llama-3.3-70b-versatile": Pricing(usd_per_1m_input=0.59, usd_per_1m_output=0.79),
    "llama-3.1-8b-instant": Pricing(usd_per_1m_input=0.05, usd_per_1m_output=0.08),
    "openai/gpt-oss-120b": Pricing(usd_per_1m_input=0.15, usd_per_1m_output=0.75),
    "moonshotai/kimi-k2-instruct": Pricing(usd_per_1m_input=1.00, usd_per_1m_output=3.00),
    # OpenAI
    "gpt-4o": Pricing(usd_per_1m_input=2.50, usd_per_1m_output=10.00),
    "gpt-4o-mini": Pricing(usd_per_1m_input=0.15, usd_per_1m_output=0.60),
    # Anthropic
    "claude-sonnet-4-5": Pricing(usd_per_1m_input=3.00, usd_per_1m_output=15.00),
    "claude-haiku-4-5": Pricing(usd_per_1m_input=1.00, usd_per_1m_output=5.00),
    # Test doubles
    "a-model": Pricing(usd_per_1m_input=1.00, usd_per_1m_output=1.00),
}


def pricing_for(model: str) -> Pricing:
    if model not in PRICING:
        raise KeyError(
            f"no pricing entry for {model!r}. Add one to PRICING rather than "
            "reporting an unpriced run as free."
        )
    return PRICING[model]
