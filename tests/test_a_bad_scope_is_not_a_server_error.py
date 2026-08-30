"""A scope that matches nothing is the caller's mistake, and it must say so.

The Cartographer raises a good error when a scope selects no files: it names
the scope, names the root, and explains why it refuses -- "Reviewing nothing
and reporting nothing reads as a clean bill of health." The server let that
propagate, so FastAPI returned 500 with the body "Internal Server Error" and
the interface showed exactly that.

Found by driving the interface: the scope field defaulted to `backend`, which
is not a directory in most repositories, so the first thing a new user saw
after choosing a folder was a server crash with no indication that a field
they never touched had caused it.

The engine's sentence is the useful one. This asserts it reaches the caller
with a status that says whose mistake it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from augury.server.app import build


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Resolved, because macOS hands out /var/... and resolves it to
    # /private/var/..., and the allowed-roots check compares resolved paths.
    # Without this the fixture returns 400 for the wrong reason and the test
    # asserting 400 passes without exercising anything.
    tmp_path = tmp_path.resolve()
    # The module reads AUGURY_ALLOWED_ROOTS once, at import, so setting the
    # variable here would reach nothing and every request would be refused for
    # a reason unrelated to what this file is about.
    import augury.server.app as server

    monkeypatch.setattr(server, "ALLOWED_ROOTS", (tmp_path,))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    build: .\n", encoding="utf-8"
    )
    return tmp_path


def test_a_scope_matching_nothing_is_a_client_error(repo: Path) -> None:
    client = TestClient(build())

    answer = client.post("/api/discover", json={"path": str(repo), "scope": "backend"})

    assert answer.status_code == 400


def test_the_engines_own_sentence_reaches_the_caller(repo: Path) -> None:
    """Not a generic message written at the boundary. The mapper explains why
    an empty review is refused, and that reasoning is the thing worth showing."""
    client = TestClient(build())

    answer = client.post("/api/discover", json={"path": str(repo), "scope": "backend"})

    detail = answer.json()["detail"]
    assert "backend" in detail
    assert "clean bill of health" in detail


def test_a_scope_that_matches_is_unaffected(repo: Path) -> None:
    client = TestClient(build())

    answer = client.post("/api/discover", json={"path": str(repo), "scope": "app"})

    assert answer.status_code == 200
    assert answer.json()["modules"]


def test_no_scope_reviews_the_whole_repository(repo: Path) -> None:
    client = TestClient(build())

    answer = client.post("/api/discover", json={"path": str(repo), "scope": ""})

    assert answer.status_code == 200
