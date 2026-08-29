"""Not paying for a decision with one possible answer.

Triage narrows the specialists a module's signals allow. When the signals allow
exactly one, there is nothing to narrow: the call costs a prompt, a response
and a slot against the provider's tokens-per-minute ceiling, and the only
answer it can give is the one already known.

That ceiling is the real constraint. A full-coverage run is token-bound, not
latency-bound -- adding concurrency past the limit produces 429s, not speed --
so the way to go faster is to send fewer tokens.
"""

from __future__ import annotations

import asyncio

from augury.agents.triage import Triage
from augury.core.cartography import ModuleNode, Signal


class _CountingModel:
    """Records every call, so a skipped one is visible."""

    model_id = "test-model"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def usage(self):  # type: ignore[no-untyped-def]
        from augury.core.adapters.base import Usage

        return Usage()

    async def structured(self, *, prompt: str, schema):  # type: ignore[no-untyped-def]
        self.calls += 1
        return schema(specialists=["data"], reasoning="because")

    async def call(self, *, prompt: str, schema):  # type: ignore[no-untyped-def]
        from augury.core.adapters.base import Completion, Usage

        self.calls += 1
        return Completion(
            result=schema(specialists=["data"], reasoning="because"),
            usage=Usage(),
            retries=0,
        )


def _module(*signals: Signal) -> ModuleNode:
    return ModuleNode(path="app/db.py", loc=40, signals=frozenset(signals))


def _choose(model: _CountingModel, module: ModuleNode) -> list[str]:
    chosen = asyncio.run(Triage(model).route(module, source="source", language="python"))
    return [layer.name for layer in chosen]


def test_one_possible_specialist_costs_no_call() -> None:
    model = _CountingModel()

    chosen = _choose(model, _module(Signal.DATA))

    assert chosen == ["data"]
    assert model.calls == 0, "paid for a decision with one possible answer"


def test_two_possible_specialists_still_ask() -> None:
    model = _CountingModel()

    _choose(model, _module(Signal.DATA, Signal.CONCURRENCY))

    assert model.calls == 1


def test_no_signal_costs_no_call_and_routes_nowhere() -> None:
    model = _CountingModel()

    assert _choose(model, _module()) == []
    assert model.calls == 0
