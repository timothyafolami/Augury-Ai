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
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from augury.core.adapters.base import ChatModel, Completion, Usage

T = TypeVar("T", bound=BaseModel)


# The model every committed recording was made with. Replaying is reproducing
# one particular run, so the model is part of what is being reproduced -- and
# a run under a different model is a different run, not a missing cassette.
RECORDED_WITH = "openai/gpt-oss-120b"

# Written beside the recordings so a replay can say what they are of. Without
# it a mismatch is indistinguishable from an incomplete set.
MANIFEST = "recorded-with.json"


def models_in(directory: Path) -> tuple[str, ...]:
    """Which models these recordings were made with, if they say."""
    manifest = directory / MANIFEST
    if not manifest.is_file():
        return ()
    try:
        said = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    models = said.get("models", [])
    return tuple(str(name) for name in models) if isinstance(models, list) else ()


def miss_report(*, model_id: str, directory: Path, recorded: tuple[str, ...]) -> str:
    """Why this call found no recording, and what to do about it.

    The first version said "run `make eval-live` to record, or check the
    cassettes are committed". Both suggestions were wrong for the failure that
    actually happened: the cassettes were committed and complete, they were of
    a different model, and re-recording would have overwritten a good set to
    answer a question nobody asked.
    """
    if recorded and not any(model_id.endswith(name) for name in recorded):
        return (
            f"these recordings are of {', '.join(recorded)}, and this run is asking "
            f"{model_id}. Replaying reproduces one particular run, so the model is "
            "part of what is reproduced. Set AUGURY_PROVIDER and AUGURY_MODEL to "
            "match, or use `make eval-replay`, which pins them for you."
        )
    return (
        f"no recording for this call to {model_id} in {directory}. "
        "Run `make eval-live` to record, or check the cassettes are committed."
    )


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

    async def call(self, *, prompt: str, schema: type[T]) -> Completion:
        """A recorded answer costs nothing, and says so.

        Replaying is free by construction, so a replayed call reports zero
        usage rather than the price the original run paid. A report built
        entirely from cassettes should read as costing nothing, because it did.
        """
        before = self._usage
        result = await self.structured(prompt=prompt, schema=schema)
        return Completion(result=result, usage=self._usage - before, retries=0)

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        path = self._path_for(prompt, schema)

        recorded = self._replay(path, schema)
        if recorded is not None:
            return recorded

        if self._replay_only:
            raise CassetteMiss(
                miss_report(
                    model_id=self._inner.model_id,
                    directory=self._dir,
                    recorded=models_in(self._dir),
                )
            )

        # One live call per key even when several agents ask at once.
        async with self._locks[path]:
            recorded = self._replay(path, schema)
            if recorded is not None:
                return recorded

            # Per-call, from the Completion. Reading the inner adapter's
            # cumulative total before and after does not work once calls run
            # concurrently -- and the specialists run under asyncio.gather with
            # a per-prompt lock, so they overlap by design. Every sibling that
            # finished in between used to land inside the delta.
            completion = await self._inner.call(prompt=prompt, schema=schema)
            self._usage = self._usage + completion.usage
            result = cast("T", completion.result)
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
