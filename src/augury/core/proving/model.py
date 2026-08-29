"""What a generated experiment is, and what running it produced."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from augury.core.schemas import Outcome


class Experiment(BaseModel):
    """A standalone script that measures one prediction's metric."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    explanation: str = Field(
        default="",
        description="What it does and why that measures the claim. Recorded "
        "because a number nobody can account for is not evidence.",
    )


class Proof(BaseModel):
    """What happened when the experiment ran."""

    model_config = ConfigDict(frozen=True)

    measured: float | None
    outcome: Outcome
    detail: str = ""
    script_path: str = Field(
        default="",
        description="Where the generated source was written before it ran. "
        "Executing generated code without recording it is unauditable.",
    )
    seconds: float = 0.0
