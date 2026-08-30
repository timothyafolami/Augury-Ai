"""The deterministic passes are synchronous, and they do network I/O.

The registry asks pypi.org and the changelog search asks a search engine, both
with blocking sockets, and both were called straight from the async handler. So
while a review was reading dependencies the event loop was not running, the
server-sent events stopped arriving, and the interface sat on the last thing it
had heard.

That fails in the most misleading way available: it looks exactly like a slow
model, so the natural response is to blame the provider.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("src/augury/server/app.py").read_text(encoding="utf-8")


def _review_body() -> ast.AsyncFunctionDef:
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_review":
            return node
    raise AssertionError("_review is gone")


def _called_directly(name: str) -> bool:
    """Whether the async body calls this without handing it to a thread."""
    for node in ast.walk(_review_body()):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        called = getattr(target, "id", None) or getattr(target, "attr", None)
        if called != name:
            continue
        # A call inside an `await asyncio.to_thread(...)` appears as an
        # argument rather than as the callee, so reaching here as the callee
        # means it runs on the loop.
        return True
    return False


def test_the_registry_is_not_asked_from_the_event_loop() -> None:
    assert not _called_directly("dependency_audit"), (
        "dependency_audit does blocking network I/O and is called on the loop"
    )


def test_the_search_is_not_made_from_the_event_loop() -> None:
    assert not _called_directly("changelog_notes"), (
        "changelog_notes does blocking network I/O and is called on the loop"
    )


def test_the_repository_is_not_walked_on_the_event_loop() -> None:
    """Mapping a large repository is seconds of synchronous file reading."""
    assert not _called_directly("map"), "the cartographer walks the disk on the loop"


def test_the_blocking_work_is_handed_to_a_thread() -> None:
    assert "to_thread" in SOURCE, "nothing is offloaded at all"
