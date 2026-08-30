"""Fanning the run's own record out to whoever is watching it.

Trajectory already writes one line per step, deterministic ones included,
because "a summary is exactly what a reader cannot check". The interface
subscribes to that same record as it is written rather than to a second,
prettier account of it -- so a viewer watches the run, and when the pipeline
stops emitting the screen stops moving.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from augury.core.trajectory import Trajectory

# How many steps a viewer may fall behind before the oldest is discarded. A
# review that waits for a browser is a review paying a model to sit still.
DEPTH = 512

# How much of a run a viewer arriving late is caught up on. The review starts
# when the request is posted and the browser subscribes after it, so everything
# in that gap -- which model was chosen, the deployment, the map -- went to
# nobody, and the interface opened on a run that appeared to begin wherever it
# happened to catch it.
REMEMBERS = 400


@dataclass(frozen=True)
class Stage:
    """One phase of the pipeline, as the pipeline actually runs it."""

    key: str
    title: str
    detail: str
    uses_model: bool

    @staticmethod
    def all() -> tuple[Stage, ...]:
        """The five stages the CLI announces, in the order it announces them.

        Named here from what `report` prints rather than from a diagram, so
        the interface cannot show a phase the code does not run.
        """
        return (
            Stage("survey", "Surveyor", "reading the deployment before the code", False),
            Stage("map", "Cartographer", "six languages, imports, request path", False),
            Stage("schema", "Schema", "what the migrations do to live tables", False),
            Stage("specialists", "Specialists", "eight concerns, one budget", True),
            Stage("report", "Report", "five deterministic passes, then the document", False),
        )


class Watchers:
    """Everyone currently watching one run."""

    def __init__(self, depth: int = DEPTH, remembers: int = REMEMBERS) -> None:
        self._depth = depth
        self._remembers = remembers
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._so_far: list[dict[str, Any]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """A queue, already holding what this run has done so far."""
        # Sized by depth, which is how far a viewer may fall behind. The replay
        # is a separate limit and must not widen it, or a slow viewer stops
        # being dropped and the review waits for a browser.
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._depth)
        for step in self._so_far[-self._depth :]:
            with _ignoring_full():
                queue.put_nowait(step)
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Hand this step to every watcher, dropping it for any that is behind.

        Never raises and never blocks: this is called from inside the review,
        and a closed browser tab must not reach the pipeline as an exception.
        """
        self._so_far.append(event)
        if len(self._so_far) > self._remembers:
            # The front, so a reconnect lands on recent work rather than on the
            # beginning of a run that has long moved past it.
            del self._so_far[: len(self._so_far) - self._remembers]

        for queue in list(self._queues):
            if queue.full():
                # The oldest, so a viewer that reconnects sees recent work
                # rather than the beginning of a run that has moved on.
                with _ignoring_empty():
                    queue.get_nowait()
            with _ignoring_full():
                queue.put_nowait(event)


class LiveTrajectory(Trajectory):
    """The run's record, written to disk and handed to watchers at once."""

    def __init__(self, path: Path, *, watchers: Watchers) -> None:
        super().__init__(path)
        self._watchers = watchers

    def _write(self, step: dict[str, Any]) -> None:
        super()._write(step)
        self._watchers.publish(step)


class _ignoring_empty:
    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, *_: object) -> bool:
        return isinstance(kind, type) and issubclass(kind, asyncio.QueueEmpty)


class _ignoring_full:
    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, *_: object) -> bool:
        return isinstance(kind, type) and issubclass(kind, asyncio.QueueFull)
