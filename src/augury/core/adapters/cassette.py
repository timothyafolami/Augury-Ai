"""Record and replay model calls so the evaluation is reproducible for free.

Two jobs. During development it makes re-running the full evaluation cost
nothing after the first pass. At judging time it lets someone with no API key
reproduce every published number, because `replay_only` fails loudly rather
than falling through to a live call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from augury.core.adapters.base import ChatModel, Usage

T = TypeVar("T", bound=BaseModel)


class CassetteMiss(RuntimeError):
    """No recording is available for a call that may not go to the network."""


class CassetteCorrupt(CassetteMiss):
    """A recording exists but cannot be read. Names the offending file."""


class CassetteModel:
    """Wraps a `ChatModel`, serving recorded answers when it has seen the call.

    The key covers the model id, the prompt and the fully-qualified response
    schema, so a changed prompt, a changed schema or a different provider is
    correctly a different recording. Two providers sharing one cassette would
    silently falsify the cross-model comparison.
    """

    def __init__(
        self,
        inner: ChatModel,
        cassette_dir: Path,
        *,
        replay_only: bool = False,
    ) -> None:
        self._inner = inner
        self._dir = Path(cassette_dir)
        self._replay_only = replay_only
        self._usage = Usage()
        self._locks: defaultdict[Path, asyncio.Lock] = defaultdict(asyncio.Lock)

        if replay_only:
            # Creating the directory here would turn a mistyped path into
            # "go spend money re-recording" instead of "that path is wrong".
            if not self._dir.is_dir():
                raise CassetteMiss(f"cassette directory {self._dir} does not exist")
        else:
            self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def usage(self) -> Usage:
        """Spend incurred in this process. Replays contribute nothing."""
        return self._usage

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        path = self._path_for(prompt, schema)

        recorded = self._replay(path, schema)
        if recorded is not None:
            return recorded

        if self._replay_only:
            raise CassetteMiss(
                f"no recording for this call in {self._dir}. "
                "Run `make eval-live` to record, or check the cassettes are committed."
            )

        # One live call per key even when several agents ask at once.
        async with self._locks[path]:
            recorded = self._replay(path, schema)
            if recorded is not None:
                return recorded

            before = self._inner.usage
            result = await self._inner.structured(prompt=prompt, schema=schema)
            self._usage = self._usage + (self._inner.usage - before)
            self._write(path, result)
            return result

    # -- internals ---------------------------------------------------------

    def _path_for(self, prompt: str, schema: type[BaseModel]) -> Path:
        payload = json.dumps(
            {
                "model": self._inner.model_id,
                "prompt": prompt,
                "schema_id": f"{schema.__module__}.{schema.__qualname__}",
                "schema": schema.model_json_schema(),
            },
            sort_keys=True,
        )
        return self._dir / f"{hashlib.sha256(payload.encode()).hexdigest()[:32]}.json"

    @staticmethod
    def _replay(path: Path, schema: type[T]) -> T | None:
        if not path.exists():
            return None
        try:
            return schema.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise CassetteCorrupt(f"cassette {path} could not be read: {exc}") from exc

    @staticmethod
    def _write(path: Path, result: BaseModel) -> None:
        """Write via a temporary file so an interrupted run cannot leave a
        truncated cassette that `exists()` then treats as a valid hit."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)
