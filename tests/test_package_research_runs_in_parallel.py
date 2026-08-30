"""The registry lookups happen once, together, and not on the critical path.

Every specialist prompt carries the installed versions of the packages its
module imports, and `describe_versions` asked the registry one package at a
time, synchronously, while building the prompt. So the first module to import
something new stopped the review until the network answered, and it did that
inside the loop that is supposed to be running specialists concurrently.

The registry already had `facts_for_many`, which asks in a thread pool, with a
docstring explaining that sequential lookups queue until the tail exceeds the
timeout. Nothing called it.

This asserts the review asks once, for everything, before the specialists run,
so by the time a prompt needs a version the answer is already in hand.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from augury.core.reference.registry import PackageFacts


class _CountingRegistry:
    """Answers instantly, and remembers how it was asked."""

    def __init__(self) -> None:
        self.one_at_a_time: list[str] = []
        self.batches: list[tuple[str, ...]] = []
        self._known = {
            "fastapi": PackageFacts(
                name="fastapi", latest="0.115.0", summary="a web framework", released="2026-01-01"
            )
        }

    def facts_for(self, name: str) -> PackageFacts | None:
        self.one_at_a_time.append(name)
        return self._known.get(name)

    def facts_for_many(self, names: Sequence[str]) -> dict[str, PackageFacts | None]:
        asked = tuple(str(n) for n in names)
        self.batches.append(asked)
        return {name: self._known.get(name) for name in asked}


ROUTES_TO_DATA: dict[str, Any] = {"specialists": ["data"], "reasoning": "an ORM session"}
NOTHING: dict[str, Any] = {"findings": []}
NO_SYNTHESIS: dict[str, Any] = {"observations": []}


def _model() -> object:
    from tests.test_augury_arm import RoutingModel

    return RoutingModel(
        TriageDecision=ROUTES_TO_DATA,
        DraftReport=NOTHING,
        DraftSynthesis=NO_SYNTHESIS,
    )


def _repo(tmp_path: Path) -> tuple[object, Path]:
    from augury.core.cartography.mapper import Cartographer

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "api.py").write_text(
        "import fastapi\nimport httpx\n\n\ndef handler():\n    return fastapi.FastAPI()\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "store.py").write_text(
        "import sqlalchemy\n\n\ndef rows():\n    return sqlalchemy\n", encoding="utf-8"
    )
    return Cartographer(tmp_path).map(), tmp_path


def test_the_registry_is_asked_once_for_everything(tmp_path: Path) -> None:
    """One batched call, covering every package the repository imports."""
    from augury.agents.augury import AuguryReviewer

    repo, root = _repo(tmp_path)
    registry = _CountingRegistry()
    reviewer = AuguryReviewer(_model(), registry=registry)  # type: ignore[arg-type]

    asyncio.run(reviewer.review(repo, root))  # type: ignore[arg-type]

    assert registry.batches, "the batched lookup was never used"
    asked = set(registry.batches[0])
    assert {"fastapi", "httpx", "sqlalchemy"} <= asked


def test_no_package_is_looked_up_one_at_a_time(tmp_path: Path) -> None:
    """A single-package lookup during the run is a blocked event loop.

    The prefetch is only worth having if nothing afterwards goes back to the
    slow path, so this asserts the slow path is not taken at all.
    """
    from augury.agents.augury import AuguryReviewer

    repo, root = _repo(tmp_path)
    registry = _CountingRegistry()
    reviewer = AuguryReviewer(_model(), registry=registry)  # type: ignore[arg-type]

    asyncio.run(reviewer.review(repo, root))  # type: ignore[arg-type]

    assert registry.one_at_a_time == []
