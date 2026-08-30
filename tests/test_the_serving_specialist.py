"""A ninth concern, for the layer nothing could route to.

`layers.py` wired 01-machine through 08-craft, so two lab layers had no
specialist at all. One of them, 10-edge, defines the defect this project's own
taxonomy calls C1: a handler that keeps working, holding its pool connection and
its accelerator memory, for a client that hung up. Nothing could reach it.

09-writing stays unreachable and that is a decision rather than an oversight:
it is about design documents, postmortems and commit messages, and a reviewer
reading source has nothing to say about them.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.cartography.model import Signal
from augury.core.cartography.signals import IMPORT_SIGNALS
from augury.core.layers import LAYERS, specialists_for
from augury.prompts import raw


def test_the_lab_layer_that_defines_c1_now_has_a_specialist() -> None:
    assert any(layer.lab_layer == "10-edge" for layer in LAYERS)


def test_it_is_reached_by_a_signal_of_its_own() -> None:
    """A concern with no signal is a specialist nothing routes to."""
    serving = next(layer for layer in LAYERS if layer.lab_layer == "10-edge")

    assert serving.signals
    assert specialists_for(frozenset(serving.signals))


def test_a_module_that_serves_a_model_raises_it() -> None:
    reached = {name for name, signals in IMPORT_SIGNALS.items() if Signal.SERVING in signals}
    assert reached, "no import routes to the serving specialist"


def test_a_plain_web_handler_does_not_raise_it() -> None:
    """Every FastAPI service would otherwise be routed to it, which costs a
    call per module for a concern most of them do not have."""
    assert Signal.SERVING not in IMPORT_SIGNALS.get("fastapi", frozenset())
    assert Signal.SERVING not in IMPORT_SIGNALS.get("numpy", frozenset())


def test_its_brief_exists_and_names_the_mechanism() -> None:
    brief = raw("layers/serving")

    assert "is_disconnected" in brief, "C1 is the defect this layer exists for"


def test_the_writing_layer_stays_unreachable_on_purpose() -> None:
    """Stated as a decision, so a later reader does not read it as a gap."""
    assert not any(layer.lab_layer == "09-writing" for layer in LAYERS)
    assert "09-writing" in Path("src/augury/core/layers.py").read_text(encoding="utf-8")
