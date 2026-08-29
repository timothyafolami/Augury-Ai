"""A brief must not ask for a prediction in a metric no experiment can measure.

`analyst.md` tells the specialist that "a prediction naming anything else
cannot be tested", and `Prediction.metric` is a bare `str`, so a prediction in
an invented metric passes the falsifiability gate and is only discovered to be
Broken once the Prover runs. The observability brief asked for two of them --
"the gap against the real distribution" and "the series count" -- so that
specialist was instructed toward guaranteed-Broken output, inflating `broken`
for the pipeline arm alone.
"""

from __future__ import annotations

import re

import pytest

from augury.core.layers import LAYERS
from augury.core.metrics import METRICS

# The sentence that commits a brief to a number.
_ASKS_FOR_A_NUMBER = re.compile(r"[Pp]redict\b([^.]*)\.", re.DOTALL)


@pytest.mark.parametrize("layer", LAYERS, ids=lambda layer: layer.name)
def test_every_prediction_a_brief_asks_for_names_a_metric_from_the_vocabulary(
    layer: object,
) -> None:
    """Each `Predict ...` must name a metric verbatim, not describe one.

    Naming it is what the specialist copies into `Prediction.metric`, and a
    metric outside the vocabulary passes the falsifiability gate and is only
    found to be Broken once the Prover runs -- so a brief that describes the
    quantity in prose is a brief that steers toward Broken output.
    """
    brief: str = layer.brief  # type: ignore[attr-defined]
    unnamed = [
        " ".join(phrase.split())
        for phrase in _ASKS_FOR_A_NUMBER.findall(brief)
        if not any(metric in phrase for metric in METRICS)
        # A brief may decline to predict, provided it says so explicitly.
        and "prediction` null" not in phrase
    ]
    assert unnamed == [], (
        f"{layer.name} asks for predictions that name no vocabulary metric: "  # type: ignore[attr-defined]
        f"{unnamed}. The vocabulary is {sorted(METRICS)}"
    )
