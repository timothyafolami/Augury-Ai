"""Which specialist owns which concern, and where its knowledge comes from.

Each specialist is one layer of the practice lab. That is not a naming
coincidence: the lab is the source of what a finding in that concern should
look like, so the specialist that hunts a defect is the one that owns the layer
defining it. Eight instances of one configuration, not eight bespoke agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from augury.core.cartography import Signal
from augury.prompts import raw


@dataclass(frozen=True)
class Layer:
    """One specialist: what it owns, what it knows, and where that came from."""

    name: str
    signals: frozenset[Signal]
    lab_layer: str

    @property
    def brief(self) -> str:
        """The specialist's instructions, loaded from its versioned prompt."""
        return raw(f"layers/{self.name}")


LAYERS: tuple[Layer, ...] = (
    Layer(
        name="concurrency",
        signals=frozenset({Signal.CONCURRENCY}),
        lab_layer="01-machine",
    ),
    Layer(
        name="network",
        signals=frozenset({Signal.NETWORK, Signal.ENTRYPOINT}),
        lab_layer="02-network",
    ),
    Layer(
        name="data",
        signals=frozenset({Signal.DATA}),
        lab_layer="03-data",
    ),
    Layer(
        name="distributed",
        signals=frozenset({Signal.DISTRIBUTED}),
        lab_layer="04-distributed",
    ),
    Layer(
        name="failure",
        signals=frozenset({Signal.FAILURE}),
        lab_layer="05-failure",
    ),
    Layer(
        name="observability",
        signals=frozenset({Signal.OBSERVABILITY}),
        lab_layer="06-observability",
    ),
    Layer(
        name="security",
        signals=frozenset({Signal.SECURITY}),
        lab_layer="07-security",
    ),
    Layer(
        name="craft",
        signals=frozenset({Signal.CRAFT}),
        lab_layer="08-craft",
    ),
    Layer(
        name="serving",
        signals=frozenset({Signal.SERVING}),
        lab_layer="10-edge",
    ),
    # 09-writing has no specialist and will not get one. It is about design
    # documents, postmortems and commit messages, and a reviewer reading source
    # has nothing to say about them. Recorded here so a later reader sees a
    # decision rather than a gap.
)


@cache
def layer_for(signal: Signal) -> Layer | None:
    """The specialist that owns this concern."""
    return next((layer for layer in LAYERS if signal in layer.signals), None)


def specialists_for(signals: frozenset[Signal]) -> tuple[Layer, ...]:
    """The specialists a module's signals justify, in declaration order.

    Declaration order rather than signal order, so two runs over the same file
    produce the same sequence and remain comparable.
    """
    return tuple(layer for layer in LAYERS if layer.signals & signals)
