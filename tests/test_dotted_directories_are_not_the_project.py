"""A dotted directory is tool state, and reviewing it spends the budget on it.

The exclusion table named specific directories -- `.venv`, `.next`, `.tox` --
and so anything dotted that was not on the list was reviewed as project
source. In one real repository `.claude/worktrees/angry-mclaren-bd82e0/` held
**366 of 476 mapped modules**: three git worktrees, each a full copy of the
application. The scheduler ranked those copies alongside the real `src/`, the
budget went to duplicates, and files the reviewer cared about were never
reached.

The general rule is the right one. A leading dot is the convention for
"belongs to a tool, not to the program": editor state, CI caches, coverage
output, agent worktrees. A repository that wants one reviewed can scope to it
explicitly, which is a decision someone makes rather than a default nobody
chose.

Every exclusion is reported with its reason, so this is a stated omission
rather than a silent one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.cartography.mapper import Cartographer


def _mapped(root: Path) -> set[str]:
    return {module.path for module in Cartographer(root).map().modules}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("value = 1\n", encoding="utf-8")
    return tmp_path


def test_an_agent_worktree_is_not_the_project(repo: Path) -> None:
    """The case that prompted this: copies of the repository under .claude."""
    worktree = repo / ".claude" / "worktrees" / "angry-mclaren" / "src"
    worktree.mkdir(parents=True)
    (worktree / "main.py").write_text("value = 2\n", encoding="utf-8")

    assert _mapped(repo) == {"src/main.py"}


@pytest.mark.parametrize(
    "dotted", [".claude", ".idea", ".vscode", ".cache", ".pytest_cache", ".terraform", ".gradle"]
)
def test_any_dotted_directory_stays_out(repo: Path, dotted: str) -> None:
    inside = repo / dotted / "pkg"
    inside.mkdir(parents=True)
    (inside / "thing.py").write_text("value = 3\n", encoding="utf-8")

    assert _mapped(repo) == {"src/main.py"}


def test_the_exclusion_says_why(repo: Path) -> None:
    """A file dropped without a reason is a file a reader has to notice."""
    (repo / ".claude").mkdir()
    (repo / ".claude" / "thing.py").write_text("value = 4\n", encoding="utf-8")

    excluded = Cartographer(repo).map().excluded

    assert ".claude" in excluded
    assert len(excluded[".claude"].reason.split()) >= 6


def test_a_dotted_file_is_still_read(repo: Path) -> None:
    """The rule is about directories. `.eslintrc.js` is configuration someone
    wrote, sitting in the project, and it is one file rather than a tree."""
    (repo / ".eslintrc.js").write_text("module.exports = {};\n", encoding="utf-8")

    assert ".eslintrc.js" in _mapped(repo)


def test_reviewing_a_dotted_directory_on_purpose_still_works(tmp_path: Path) -> None:
    """The root's own name is not a reason to refuse it.

    Someone who points the reviewer at `~/.config/thing` has said what they
    want, and the rule is about directories inside the tree rather than the
    tree itself.
    """
    root = tmp_path / ".config" / "thing"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("value = 5\n", encoding="utf-8")

    assert _mapped(root) == {"src/main.py"}
