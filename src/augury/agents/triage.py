"""Deciding who should read a file, before anyone does.

Routing is where the cost is decided. Sending every module to all eight
specialists would cost eight times as much and produce seven confident opinions
from reviewers with nothing to look at, which is worse than expensive: it
teaches the user to skim the report.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict

from augury.core.adapters.base import ChatModel
from augury.core.cartography import ModuleNode
from augury.core.layers import Layer, specialists_for
from augury.core.trajectory import Trajectory
from augury.prompts import render


class TriageDecision(BaseModel):
    """Which specialists this file warrants, and why."""

    model_config = ConfigDict(extra="ignore")

    # Required, for the same reason DraftFinding's fields are: a strict
    # provider rejects a response whose schema declares an optional property.
    specialists: list[str]
    reasoning: str


class Triage:
    """Narrows the specialists a module's signals allow to the ones it needs."""

    def __init__(self, model: ChatModel, *, trajectory: Trajectory | None = None) -> None:
        self._model = model
        self._trace = trajectory

    async def route(
        self, module: ModuleNode, source: str, language: str, context: str = ""
    ) -> list[Layer]:
        """The specialists to invoke, in declaration order.

        Static signals bound the choice: a specialist whose concern was never
        detected is not offered, so the model can narrow but never widen. That
        keeps a hallucinated layer name from buying a real model call.
        """
        allowed = specialists_for(module.signals)
        if not allowed:
            return []

        # Nothing to narrow. The call would cost a prompt, a response and a
        # slot against the provider's tokens-per-minute ceiling, and the only
        # answer available is the one already in hand. That ceiling is the real
        # constraint on a full-coverage run: it is token-bound rather than
        # latency-bound, so sending fewer tokens is what makes it faster.
        if len(allowed) == 1:
            if self._trace is not None:
                self._trace.record(
                    agent="triage",
                    action="skipped",
                    detail={
                        "path": module.path,
                        "specialists": [layer.name for layer in allowed],
                        "why": "one specialist allowed, so there was nothing to narrow",
                    },
                )
            return list(allowed)

        prompt = render(
            "triage",
            path=module.path,
            language=language,
            loc=module.loc,
            fan_in=module.fan_in,
            signals=", ".join(sorted(s.value for s in module.signals)),
            source=source,
            context=context or "(none found)",
            specialists="\n".join(f"- {layer.name}: {layer.lab_layer}" for layer in allowed),
        )
        completion = await self._model.call(prompt=prompt, schema=TriageDecision)
        decision = cast("TriageDecision", completion.result)
        if self._trace is not None:
            self._trace.record_call(
                agent=f"triage:{module.path}",
                prompt=prompt,
                response=decision.model_dump(),
                usage=completion.usage,
                retries=completion.retries,
            )

        chosen = {name.strip().lower() for name in decision.specialists}
        return [layer for layer in allowed if layer.name in chosen]
