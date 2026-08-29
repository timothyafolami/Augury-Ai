"""Walk a repository and build the map the Scheduler steers by.

Best-effort by design: a file that does not parse is recorded in `unparsed`
rather than aborting the review, because real repositories contain broken
files and a reviewer that dies on one is useless.
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path

from augury.core.cartography.languages import EXTENSIONS, ParseError, adapter_for
from augury.core.cartography.model import ModuleNode, RepoMap, Signal

# A single source file has no legitimate reason to be larger than this. The cap
# bounds memory, and it stops a binary shipped with a source extension from
# becoming replacement-character soup that is parsed and then tokenised at cost.
MAX_SOURCE_BYTES = 256 * 1024

# Files that set the conditions source code runs under. A pool size is only
# wrong relative to a worker count, and the worker count lives here. Sent with
# every module, so this list stays short and each entry is trimmed.
CONTEXT_FILES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "gunicorn.conf.py",
    "uvicorn.json",
    "Procfile",
)

# Enough to carry a CMD line and a service block, not a whole manifest.
MAX_CONTEXT_CHARS = 4_000

# Directories that hold somebody else's code. Run against a production
# repository the mapper reported 1,137 modules, 843 of which were a bundled
# `.conda` environment -- so three quarters of the map, and three quarters of
# any budget spent from it, was a vendored standard library. `.venv` and
# `site-packages` were listed here and `.conda` was not.
#
# Matched at any depth, because a monorepo nests one of these per package.
EXCLUDED_DIRS = frozenset(
    {
        # Python environments and build output
        ".venv",
        "venv",
        "env",
        ".conda",
        "conda",
        ".tox",
        ".nox",
        "site-packages",
        "dist-packages",
        "__pycache__",
        "eggs",
        ".eggs",
        "*.egg-info",
        # JavaScript and TypeScript
        "node_modules",
        "bower_components",
        ".next",
        ".nuxt",
        ".svelte-kit",
        # Other ecosystems
        "vendor",
        "third_party",
        "Pods",
        ".gradle",
        "target",
        # Tooling and build artefacts
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "build",
        "dist",
        "coverage",
        "htmlcov",
    }
)


class Cartographer:
    """Builds a `RepoMap` from a repository root."""

    def __init__(
        self,
        root: Path,
        *,
        scope: tuple[str, ...] = (),
        entrypoints: tuple[str, ...] = (),
    ) -> None:
        """`scope` limits the map to these repo-relative directories.

        A repository is a set of services, and reviewing all of them at once
        ranks a React component and a Celery worker on one scale. The survey
        names the directories each service is built from; this is how that
        answer is used.
        """
        self._root = Path(root)
        self._scope = tuple(part.strip("/") for part in scope if part.strip("/"))
        # Modules a service command says it starts. A Celery worker's module
        # looks like nothing to a signal detector, so without these every
        # background task in the repository is unreachable.
        self._entrypoints = tuple(part.strip("/") for part in entrypoints if part.strip("/"))

    def map(self) -> RepoMap:
        sources = sorted(self._source_files())
        if self._scope and not sources:
            raise ValueError(
                f"scope {list(self._scope)} matched no files under {self._root}. "
                "Reviewing nothing and reporting nothing reads as a clean bill of health."
            )
        index = self._index(sources)

        nodes: list[ModuleNode] = []
        unparsed: list[str] = []
        skipped: dict[str, str] = {}
        churn = self._churn()

        for path in sources:
            rel = self._relative(path)

            reason = self._refuse(path)
            if reason is not None:
                skipped[rel] = reason
                continue
            adapter = adapter_for(path)
            if adapter is None:  # unreachable: _source_files filters by extension
                continue

            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                parsed = adapter.parse(text, package=self._package_of(path))
            except ParseError:
                unparsed.append(rel)
                continue

            resolved = {
                target
                for name in parsed.imports
                if (target := self._resolve(name, index)) is not None
            }
            # Dynamic imports, resolved by exact match only. A real import may
            # fall back to its package -- `from src.tasks import x` legitimately
            # depends on `src/tasks/__init__.py` -- but a bare string must not,
            # or every unknown dotted name silently becomes an edge to the
            # nearest package that happens to exist.
            resolved |= {
                target
                for name in parsed.named_in_strings
                if (target := index.get(name)) is not None
            }
            nodes.append(
                ModuleNode(
                    path=rel,
                    loc=parsed.loc,
                    imports=frozenset(resolved - {rel}),  # a self-edge is not blast radius
                    signals=parsed.signals,
                    # A module in this repository is not an unrecognised
                    # library; it simply has not been read yet.
                    unmatched_imports=frozenset(
                        name
                        for name in parsed.unmatched_imports
                        if self._resolve(name, index) is None
                    ),
                    # Third-party only: a name that resolves to a module in
                    # this repository is not a dependency to look up.
                    external=frozenset(
                        name for name in parsed.third_party if self._resolve(name, index) is None
                    ),
                    churn=churn.get(rel, 0),
                )
            )

        modules = _with_depth(self._with_fan_in(nodes), declared=self._entrypoints)
        unreachable = tuple(
            sorted(m.path for m in modules if m.depth is None)
            if any(m.depth is not None for m in modules)
            else ()
        )

        return RepoMap(
            root=str(self._root),
            modules=modules,
            unparsed=unparsed,
            unreachable=unreachable,
            skipped=skipped,
            context=self._context(),
        )

    def _context(self) -> dict[str, str]:
        """Deployment configuration, trimmed.

        Only the named files: this is sent with every module, so anything here
        is paid for many times over and earns its place only by changing how
        the module reads. A .env is never collected -- context reaches a model
        and a committed recording, and a secret belongs in neither.
        """
        found: dict[str, str] = {}
        for name in CONTEXT_FILES:
            path = self._root / name
            if not path.is_file() or path.is_symlink():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            found[name] = text[:MAX_CONTEXT_CHARS]
        return found

    def _refuse(self, path: Path) -> str | None:
        """Why this file will not be read, or None to read it.

        Symlinks are refused because the name is attacker-controlled and the
        target is not: `config.py -> ~/.aws/credentials` is a valid repository
        and a .env is largely valid Python, so it parses and survives into a
        prompt and from there into a committed recording.
        """
        if path.is_symlink():
            return "symlink"
        if path.stat().st_size > MAX_SOURCE_BYTES:
            return "larger than the source size cap"
        return None

    # -- traversal ---------------------------------------------------------

    def _source_files(self) -> list[Path]:
        return [
            path
            for path in self._root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in EXTENSIONS
            and not EXCLUDED_DIRS & set(path.relative_to(self._root).parts)
            and self._in_scope(path)
        ]

    def _in_scope(self, path: Path) -> bool:
        if not self._scope:
            return True
        relative = path.relative_to(self._root).as_posix()
        return any(relative == part or relative.startswith(f"{part}/") for part in self._scope)

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
            if path.suffix != ".py":  # only Python names are dotted module paths
                continue
            rel = self._relative(path)
            for name in self._names_for(path):
                # On a collision, a package __init__ wins: it is the name the
                # interpreter would bind, and it keeps resolution deterministic.
                if name not in index or path.name == "__init__.py":
                    index[name] = rel
        return index

    # A suffix shorter than this is too ambiguous to be worth registering:
    # `pipeline` names four files in a real repository, `tasks.pipeline` names
    # one.
    MIN_SUFFIX_SEGMENTS = 2

    def _names_for(self, path: Path) -> set[str]:
        """Every dotted name this module can plausibly be imported by.

        Both the repository-relative name and the package-relative one, plus
        every dotted suffix between them. A service built from `./backend` with
        `PYTHONPATH=/app` imports `backend/src/tasks/pipeline.py` as
        `src.tasks.pipeline`, which is neither of the two endpoints -- and
        missing it left an entire Celery task layer unreachable.
        """
        names: set[str] = set()
        for base in (self._root, self._package_root(path)):
            full = self._dotted(path, base)
            if not full:
                continue
            names.add(full)
            segments = full.split(".")
            for start in range(1, len(segments) - self.MIN_SUFFIX_SEGMENTS + 1):
                names.add(".".join(segments[start:]))
        return names

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

    # -- resolution --------------------------------------------------------

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


def _git_environment() -> dict[str, str]:
    """The minimum git needs, and nothing a reviewed repository could have set."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _with_depth(nodes: list[ModuleNode], *, declared: tuple[str, ...] = ()) -> list[ModuleNode]:
    """Hops from the nearest entrypoint, by breadth-first walk of the imports.

    Fan-in asks how many modules import this one, which is popularity, and the
    most popular module in a service is usually its settings. Depth asks
    whether a request reaches it and how soon, which is the question a reviewer
    has.

    None where no entrypoint reaches the module. When the repository declares
    no entrypoint at all, every depth stays None rather than defaulting to
    zero: a library has no request path and inventing one would be a guess.
    """
    named = {stem.strip("/") for stem in declared}
    frontier = [
        n for n in nodes if Signal.ENTRYPOINT in n.signals or n.path.rsplit(".", 1)[0] in named
    ]
    if not frontier:
        return nodes

    by_path = {n.path: n for n in nodes}
    depth = {n.path: 0 for n in frontier}
    while frontier:
        following = []
        for node in frontier:
            for imported in node.imports:
                if imported in depth or imported not in by_path:
                    continue
                depth[imported] = depth[node.path] + 1
                following.append(by_path[imported])
        frontier = following

    return [n.model_copy(update={"depth": depth.get(n.path)}) for n in nodes]
