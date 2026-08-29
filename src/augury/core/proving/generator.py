"""Asking a model to write the experiment that settles a claim."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from augury.core.adapters.base import ChatModel
from augury.core.findings import Finding
from augury.core.proving.model import Experiment
from augury.prompts import render


class GeneratedExperiment(BaseModel):
    """What the model returns. Every field required, null never absent."""

    model_config = ConfigDict(extra="ignore")

    source: str
    explanation: str
    refusal: str


class Generator:
    """Writes an experiment for a finding, or declines to."""

    def __init__(self, model: ChatModel) -> None:
        self._model = model

    async def __call__(self, finding: Finding, root: Path) -> Experiment:
        prediction = finding.prediction
        if prediction is None:  # pragma: no cover - the caller checks first
            raise ValueError("nothing to measure: the finding carries no prediction")

        source = ""
        candidate = root / finding.path
        if candidate.is_file():
            source = candidate.read_text(encoding="utf-8", errors="replace")[:20_000]

        prompt = render(
            "experiment",
            path=finding.path,
            symbol=finding.symbol,
            mechanism=finding.mechanism,
            metric=prediction.metric,
            comparator=prediction.comparator.value,
            value=f"{prediction.value:g}",
            unit=prediction.unit,
            condition=prediction.condition,
            language=Path(finding.path).suffix.lstrip(".") or "text",
            source=source,
        )
        written = await self._model.structured(prompt=prompt, schema=GeneratedExperiment)

        if written.refusal.strip():
            # A refusal is an answer. Fabricating a script that cannot measure
            # the claim would produce a number nobody should believe.
            raise CannotMeasure(written.refusal.strip())
        return Experiment(source=written.source, explanation=written.explanation)


class CannotMeasure(Exception):
    """The claim cannot be settled without something this must not touch."""
