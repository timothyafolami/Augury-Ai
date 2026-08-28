"""Churn is one of the three inputs the Scheduler steers by.

It comes from `git log`, which is a subprocess whose output format has sharp
edges. When it silently returns nothing, `recency` becomes a constant for the
whole repository and nobody notices.
"""

import subprocess
from pathlib import Path

from augury.core.cartography import Cartographer


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", f"touch {rel}")


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    return tmp_path


def test_counts_commits_that_touched_each_file(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    commit(root, "app/hot.py", "x = 1\n")
    commit(root, "app/hot.py", "x = 2\n")
    commit(root, "app/cold.py", "y = 1\n")

    repo = Cartographer(root).map()

    assert repo.module("app/hot.py").churn == 2
    assert repo.module("app/cold.py").churn == 1


def test_churn_survives_mapping_a_subdirectory(tmp_path: Path) -> None:
    """git log prints paths from the repository top level regardless of -C, so
    mapping one service in a monorepo silently zeroed churn everywhere."""
    root = make_repo(tmp_path)
    commit(root, "services/api/app.py", "x = 1\n")
    commit(root, "services/api/app.py", "x = 2\n")

    repo = Cartographer(root / "services" / "api").map()

    assert repo.module("app.py").churn == 2


def test_churn_survives_a_non_ascii_path(tmp_path: Path) -> None:
    """git quotes non-ASCII paths as octal escapes by default, which never
    matches the real path, so those files reported churn=0."""
    root = make_repo(tmp_path)
    commit(root, "app/café.py", "x = 1\n")

    assert Cartographer(root).map().module("app/café.py").churn == 1


def test_a_directory_without_git_history_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")

    assert Cartographer(tmp_path).map().module("app.py").churn == 0
