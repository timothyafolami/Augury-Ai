"""Recording must not double-count concurrent spend.

`ProviderAdapter.usage` is cumulative, matching provider SDKs. Bracketing it --
read before, read after, add the difference -- is wrong the moment two calls
overlap, because every sibling that finished in between lands inside the delta.
`Completion` exists precisely so callers never have to do that.

CassetteModel reintroduced the bracket, and the specialists run under
`asyncio.gather` with a per-prompt lock, so they overlap by design. Record mode
is the only configuration that reports a non-zero cost, and it was the one
inflating it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from augury.core.adapters.base import Completion, Usage
from augury.core.adapters.cassette import CassetteModel


class _Answer(BaseModel):
    value: str


class _CumulativeModel:
    """Shaped like ProviderAdapter: usage accumulates for the life of the object."""

    model_id = "test-model"

    def __init__(self) -> None:
        self._usage = Usage()
        self.release: asyncio.Event = asyncio.Event()

    @property
    def usage(self) -> Usage:
        return self._usage

    async def call[T: BaseModel](self, *, prompt: str, schema: type[T]) -> Completion:
        one = Usage(input_tokens=100, output_tokens=100, usd=1.0)
        if prompt == "slow":
            await self.release.wait()
        self._usage = self._usage + one
        return Completion(result=schema(value=prompt), usage=one, retries=0)

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        return cast("T", (await self.call(prompt=prompt, schema=schema)).result)


def test_two_overlapping_recordings_cost_what_they_cost(tmp_path: Path) -> None:
    inner = _CumulativeModel()
    cassette = CassetteModel(inner, tmp_path)

    async def both() -> None:
        slow = asyncio.create_task(cassette.structured(prompt="slow", schema=_Answer))
        await asyncio.sleep(0)
        # The fast call completes entirely inside the slow call's bracket.
        await cassette.structured(prompt="fast", schema=_Answer)
        inner.release.set()
        await slow

    asyncio.run(both())

    assert inner.usage.usd == 2.0, "two calls really were made"
    assert cassette.usage.usd == 2.0, (
        f"reported {cassette.usage.usd} for 2.0 of real spend: the cumulative "
        "counter was bracketed and the sibling landed inside the delta"
    )
