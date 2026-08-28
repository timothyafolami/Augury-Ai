"""Walk a repository and build the map the Scheduler steers by.

Best-effort by design: a file that does not parse is recorded in `unparsed`
rather than aborting the review, because real repositories contain broken
files and a reviewer that dies on one is useless.
"""

from __future__ import annotations

import ast
import subprocess
from collections import Counter
from pathlib import Path

from augury.core.cartography.model import ModuleNode, RepoMap, Signal
from augury.core.cartography.signals import signals_for_import
from augury.core.cartography.source_signals import signals_from_source

EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "site-packages",
        "build",
        "dist",
    }
)


class Cartographer:
    """Builds a `RepoMap` from a repository root."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def map(self) -> RepoMap:
        sources = sorted(self._source_files())
        index = self._index(sources)

        nodes: list[ModuleNode] = []
        unparsed: list[str] = []
        churn = self._churn()

        for path in sources:
            rel = self._relative(path)
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                unparsed.append(rel)
                continue

            imports, signals = self._analyse(tree, path, index)
            nodes.append(
                ModuleNode(
                    path=rel,
                    loc=sum(1 for line in text.splitlines() if line.strip()),
                    imports=frozenset(imports - {rel}),  # a self-edge is not blast radius
                    signals=frozenset(signals),
                    churn=churn.get(rel, 0),
                )
            )

        return RepoMap(root=str(self._root), modules=self._with_fan_in(nodes), unparsed=unparsed)

    # -- traversal ---------------------------------------------------------

    def _source_files(self) -> list[Path]:
        return [
            path
            for path in self._root.rglob("*.py")
            if not EXCLUDED_DIRS & set(path.relative_to(self._root).parts)
        ]

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix()

    # -- import index ------------------------------------------------------

    def _index(self, sources: list[Path]) -> dict[str, str]:
        """Every name a module can plausibly be imported by, mapped to its path.

        A file is reachable under more than one name: `src/pkg/a.py` is
        `pkg.a` to the interpreter but `src.pkg.a` relative to the repository
        root. Both are registered, so a src layout and a flat layout both
        resolve without the caller declaring which one they have.
        """
        index: dict[str, str] = {}
        for path in sources:
            rel = self._relative(path)
            for name in self._names_for(path):
                # On a collision, a package __init__ wins: it is the name the
                # interpreter would bind, and it keeps resolution deterministic.
                if name not in index or path.name == "__init__.py":
                    index[name] = rel
        return index

    def _names_for(self, path: Path) -> set[str]:
        return {
            name
            for base in (self._root, self._package_root(path))
            if (name := self._dotted(path, base))
        }

    @staticmethod
    def _package_root(path: Path) -> Path:
        """The first ancestor that is not itself a package.

        This is the directory the interpreter would have on its path, which is
        what turns `src/pkg/a.py` into `pkg.a`.
        """
        directory = path.parent
        while (directory / "__init__.py").exists() and directory.parent != directory:
            directory = directory.parent
        return directory

    @staticmethod
    def _dotted(path: Path, base: Path) -> str:
        try:
            parts = path.relative_to(base).with_suffix("").parts
        except ValueError:
            return ""
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _package_of(self, path: Path) -> str:
        """The package a relative import inside this file is resolved against."""
        dotted = self._dotted(path, self._package_root(path))
        if path.name == "__init__.py":
            return dotted
        package, _, _ = dotted.rpartition(".")
        return package

    # -- analysis ----------------------------------------------------------

    def _analyse(
        self, tree: ast.Module, path: Path, index: dict[str, str]
    ) -> tuple[set[str], set[Signal]]:
        imports: set[str] = set()
        signals: set[Signal] = signals_from_source(tree)
        package = self._package_of(path)

        for node in ast.walk(tree):
            for dotted in self._imported_names(node, package):
                signals |= signals_for_import(dotted.split(".")[0])
                internal = self._resolve(dotted, index)
                if internal is not None:
                    imports.add(internal)

        return imports, signals

    @staticmethod
    def _imported_names(node: ast.AST, package: str) -> list[str]:
        """Every dotted name this statement could be depending on.

        `from pkg import store` is listed as `pkg.store` before `pkg`, so the
        submodule is preferred when one exists and the package is used only
        when the imported name is not a module.
        """
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]

        if not isinstance(node, ast.ImportFrom):
            return []

        base = node.module or ""
        if node.level:
            # `from .` is this package; `from ..` is its parent, and so on.
            ancestors = package.split(".") if package else []
            prefix = ".".join(ancestors[: len(ancestors) - (node.level - 1)] or ancestors)
            base = f"{prefix}.{base}".strip(".") if base else prefix

        if not base:
            return []
        return [f"{base}.{alias.name}" for alias in node.names] + [base]

    @staticmethod
    def _resolve(dotted: str, index: dict[str, str]) -> str | None:
        """Longest matching prefix wins, so `a.b.c` prefers `a/b/c.py`."""
        candidate = dotted
        while candidate:
            if candidate in index:
                return index[candidate]
            candidate, _, _ = candidate.rpartition(".")
        return None

    @staticmethod
    def _with_fan_in(nodes: list[ModuleNode]) -> list[ModuleNode]:
        counts = Counter(target for node in nodes for target in node.imports)
        return [node.model_copy(update={"fan_in": counts[node.path]}) for node in nodes]

    # -- history -----------------------------------------------------------

    def _churn(self) -> dict[str, int]:
        """Commits touching each file. Absent history is not an error.

        `--relative` is required: git prints paths from the repository top
        level otherwise, which silently zeroes churn whenever the mapping root
        is a subdirectory. `core.quotePath=false` keeps non-ASCII paths
        matchable.
        """
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._root),
                    "-c",
                    "core.quotePath=false",
                    "log",
                    "--name-only",
                    "--relative",
                    "--pretty=format:",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        return Counter(line.strip() for line in result.stdout.splitlines() if line.strip())
