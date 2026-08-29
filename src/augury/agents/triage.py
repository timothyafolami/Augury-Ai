"""Deciding who should read a file, before anyone does.

Routing is where the cost is decided. Sending every module to all eight
specialists would cost eight times as much and produce seven confident opinions
from reviewers with nothing to look at, which is worse than expensive: it
teaches the user to skim the report.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from augury.core.adapters.base import ChatModel
from augury.core.cartography import ModuleNode
from augury.core.layers import Layer, specialists_for
from augury.prompts import render


class TriageDecision(BaseModel):
    """Which specialists this file warrants, and why."""

    model_config = ConfigDict(extra="ignore")

    specialists: list[str] = Field(default_factory=list)
    reasoning: str = ""


class Triage:
    """Narrows the specialists a module's signals allow to the ones it needs."""

    def __init__(self, model: ChatModel) -> None:
        self._model = model

    async def route(self, module: ModuleNode, source: str, language: str) -> list[Layer]:
        """The specialists to invoke, in declaration order.

        Static signals bound the choice: a specialist whose concern was never
        detected is not offered, so the model can narrow but never widen. That
        keeps a hallucinated layer name from buying a real model call.
        """
        allowed = specialists_for(module.signals)
        if not allowed:
            return []

        decision = await self._model.structured(
            prompt=render(
                "triage",
                path=module.path,
                language=language,
                loc=module.loc,
                fan_in=module.fan_in,
                signals=", ".join(sorted(s.value for s in module.signals)),
                source=source,
                specialists="\n".join(f"- {layer.name}: {layer.lab_layer}" for layer in allowed),
            ),
            schema=TriageDecision,
        )

        chosen = {name.strip().lower() for name in decision.specialists}
        return [layer for layer in allowed if layer.name in chosen]
