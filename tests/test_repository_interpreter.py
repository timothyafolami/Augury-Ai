"""Running an experiment with the repository's own Python, not ours.

A generated experiment imports the code it measures. Run with Augury's
interpreter it fails at `import jwt`, because the dependencies belong to the
repository under review and not to the reviewer -- so every proof came back
"broken: printed no number", which is true and useless.

The repository usually ships its interpreter: `.venv/`, `venv/`, `.conda/`.
Finding it is the difference between an experiment that measures the claim and
one that measures our virtualenv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from augury.core.proving.interpreter import interpreter_for

LAYOUTS = [".venv", "venv", ".conda", "env", ".virtualenv"]


@pytest.mark.parametrize("directory", LAYOUTS)
def test_a_repository_virtualenv_is_preferred(tmp_path: Path, directory: str) -> None:
    python = tmp_path / directory / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)

    assert interpreter_for(tmp_path) == python


def test_a_repository_with_no_environment_falls_back_to_ours(tmp_path: Path) -> None:
    """Better than refusing: a script with no third-party imports still runs."""
    assert interpreter_for(tmp_path) == Path(sys.executable)


def test_a_non_executable_candidate_is_not_used(tmp_path: Path) -> None:
    """A stale `.venv` directory with no usable python is not an interpreter."""
    stale = tmp_path / ".venv" / "bin" / "python"
    stale.parent.mkdir(parents=True)
    stale.write_text("")  # present, not executable

    assert interpreter_for(tmp_path) == Path(sys.executable)


def test_a_scoped_review_finds_the_environment_beside_the_service(
    tmp_path: Path,
) -> None:
    """The venv lives in `backend/`, and the review is scoped to `backend/`."""
    python = tmp_path / "backend" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)

    assert interpreter_for(tmp_path / "backend") == python


def test_the_search_does_not_escape_the_repository(tmp_path: Path) -> None:
    """A venv above the repository belongs to something else."""
    outside = tmp_path / ".venv" / "bin" / "python"
    outside.parent.mkdir(parents=True)
    outside.write_text("#!/bin/sh\n")
    outside.chmod(0o755)
    inner = tmp_path / "project"
    inner.mkdir()

    assert interpreter_for(inner) == Path(sys.executable)
