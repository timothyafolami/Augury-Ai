"""The registry that turns a detected signal into a specialist that can act.

This is the connective tissue: cartography reports a Signal, the registry names
the specialist that owns it, and the specialist's brief and corpus come from
the practice lab layer that defines the concern. If a signal has no specialist,
detecting it was pointless.
"""

import pytest

from augury.core.cartography import Signal
from augury.core.layers import LAYERS, layer_for, specialists_for


@pytest.mark.parametrize("signal", list(Signal))
def test_every_signal_routes_to_a_specialist(signal: Signal) -> None:
    """A signal nobody can act on is a wasted detection and a wasted call."""
    assert layer_for(signal) is not None, f"{signal} has no specialist"


def test_every_layer_has_a_brief_that_is_not_a_placeholder() -> None:
    for layer in LAYERS:
        assert len(layer.brief.strip()) > 300, f"{layer.name} brief looks unfinished"


def test_every_layer_names_the_practice_lab_layer_it_comes_from() -> None:
    """The brief's authority is that it was written from a specific layer of
    the lab. An unsourced brief is just an opinion in a prompt."""
    for layer in LAYERS:
        assert layer.lab_layer, f"{layer.name} does not cite a lab layer"


def test_a_module_routes_only_to_the_specialists_its_signals_justify() -> None:
    chosen = specialists_for(frozenset({Signal.DATA, Signal.CONCURRENCY}))

    assert {layer.name for layer in chosen} == {"data", "concurrency"}


def test_a_module_with_no_signals_routes_to_nobody() -> None:
    """Fanning out to eight specialists on an empty file is pure spend."""
    assert specialists_for(frozenset()) == ()


def test_entrypoint_routes_to_the_network_specialist() -> None:
    """An entrypoint is where load enters, which is a network concern before
    it is anything else."""
    names = {layer.name for layer in specialists_for(frozenset({Signal.ENTRYPOINT}))}

    assert "network" in names


def test_specialists_are_returned_in_a_stable_order() -> None:
    """Run-to-run ordering changes would show up as spurious diffs in the
    changelog and make two runs incomparable."""
    signals = frozenset({Signal.SECURITY, Signal.DATA, Signal.FAILURE})

    assert specialists_for(signals) == specialists_for(signals)
