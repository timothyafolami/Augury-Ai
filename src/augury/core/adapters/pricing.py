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
    # Groq serving the open-weight gpt-oss models. Two sizes of the same model
    # family, which is what makes the capability question answerable: run the
    # same evaluation on both and see whether the result depends on model size
    # or on the architecture around it.
    "openai/gpt-oss-120b": Pricing(usd_per_1m_input=0.15, usd_per_1m_output=0.75),
    "openai/gpt-oss-20b": Pricing(usd_per_1m_input=0.10, usd_per_1m_output=0.50),
    # OpenAI
    "gpt-4o": Pricing(usd_per_1m_input=2.50, usd_per_1m_output=10.00),
    "gpt-4o-mini": Pricing(usd_per_1m_input=0.15, usd_per_1m_output=0.60),
    # Anthropic
    "claude-sonnet-4-5": Pricing(usd_per_1m_input=3.00, usd_per_1m_output=15.00),
    "claude-haiku-4-5": Pricing(usd_per_1m_input=1.00, usd_per_1m_output=5.00),
    # DeepSeek, at PEAK rates. It bills half off-peak (outside 01:00-04:00 and
    # 06:00-10:00 UTC on weekdays), and a cost that is sometimes half what was
    # reported is a cost nobody can plan against. The number here is the one
    # that is never an underestimate.
    #
    # Input is the cache-miss rate for the same reason: a cache hit is cheaper
    # and is not something this can predict per call.
    "deepseek-v4-flash": Pricing(usd_per_1m_input=0.44, usd_per_1m_output=1.32),
    "deepseek-v4-pro": Pricing(usd_per_1m_input=1.32, usd_per_1m_output=3.96),
    "deepseek-v4-flash-vision-exp": Pricing(usd_per_1m_input=0.44, usd_per_1m_output=1.32),
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
