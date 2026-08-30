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
from augury.core.cartography.model import Exclusion, ModuleNode, RepoMap, Signal

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
    # The committed templates, and only those. They are the declaration of
    # which knobs exist, which is half of every configuration defect; the file
    # they are a template of is refused by name a few lines below.
    ".env.example",
    ".env.sample",
)

# Enough to carry a CMD line and a service block, not a whole manifest.
MAX_CONTEXT_CHARS = 4_000

# Directories whose contents are tests. Matched as whole path segments, never
# as substrings: `app/contest/` and `latest.py` are production code.
TEST_DIRS = frozenset({"tests", "test", "testing", "spec", "specs", "__tests__"})

# Filename shapes that mean the same thing, across the six languages here.
TEST_PREFIXES = ("test_", "conftest")
TEST_SUFFIXES = ("_test", ".test", ".spec", "_spec")


def looks_like_a_test(relative: str) -> bool:
    """Whether this path is a test rather than the service.

    A test file has defects worth finding -- one that asserts on a mock, one
    that cannot fail -- but they are a different review with a different brief,
    and asking eight production concerns of a file that never serves a request
    is a fifth of a budget spent on the wrong question.
    """
    path = Path(relative)
    if TEST_DIRS & set(path.parts[:-1]):
        return True
    stem = path.stem
    return stem.startswith(TEST_PREFIXES) or stem.endswith(TEST_SUFFIXES)


# -- what never enters the map, and the sentence said about it ---------------
#
# Every exclusion below is reported: a category, one of these reasons, and a
# count of the files it swallowed. The reasons are shared constants rather than
# strings written at each site, so a category cannot end up with two of them
# and the count cannot drift from what it is counting.

_INSTALLED = "installed dependencies, not code this repository is answerable for"
_VENDORED = "a vendored copy of somebody else's code"
_BUILD_OUTPUT = "build output, produced from source that is itself in the map"
_TOOL_CACHE = "a tool's cache, rewritten on the next run"
_VCS_INTERNALS = "version control internals rather than source"
_EDITOR_STATE = "one developer's editor settings"
_COVERAGE_REPORT = "a coverage report, produced from a test run"
_MINIFIED = "a minified bundle: one machine-written line, and the source it came from is in the map"
_GENERATED = "written by a code generator, so a defect here belongs to the generator or its schema"
_FIXTURES = "test data rather than code that runs in production"
_UNSUPPORTED = "no adapter reads this file type, so nothing here was parsed"
_OUT_OF_SCOPE = "outside the directories this review was scoped to"
_SECRETS = "holds live credentials, so it is never opened, mapped or sent to a model"

# Directories that hold somebody else's code. Run against a production
# repository the mapper reported 1,137 modules, 843 of which were a bundled
# `.conda` environment -- so three quarters of the map, and three quarters of
# any budget spent from it, was a vendored standard library. `.venv` and
# `site-packages` were listed here and `.conda` was not.
#
# Matched at any depth, because a monorepo nests one of these per package. The
# directory name is the category the map reports, so a reader gets
# `node_modules 31204` rather than one total they cannot act on.
EXCLUDED_DIRS: dict[str, str] = {
    # Python environments and build output
    ".venv": _INSTALLED,
    "venv": _INSTALLED,
    "env": _INSTALLED,
    ".conda": _INSTALLED,
    "conda": _INSTALLED,
    ".tox": _TOOL_CACHE,
    ".nox": _TOOL_CACHE,
    "site-packages": _INSTALLED,
    "dist-packages": _INSTALLED,
    "__pycache__": _TOOL_CACHE,
    "eggs": _BUILD_OUTPUT,
    ".eggs": _BUILD_OUTPUT,
    # JavaScript and TypeScript
    "node_modules": _INSTALLED,
    "bower_components": _INSTALLED,
    ".next": _BUILD_OUTPUT,
    ".nuxt": _BUILD_OUTPUT,
    ".svelte-kit": _BUILD_OUTPUT,
    # Other ecosystems
    "vendor": _VENDORED,
    "third_party": _VENDORED,
    "Pods": _INSTALLED,
    ".gradle": _TOOL_CACHE,
    "target": _BUILD_OUTPUT,
    # Tooling and build artefacts
    ".git": _VCS_INTERNALS,
    ".hg": _VCS_INTERNALS,
    ".svn": _VCS_INTERNALS,
    ".mypy_cache": _TOOL_CACHE,
    ".pytest_cache": _TOOL_CACHE,
    ".ruff_cache": _TOOL_CACHE,
    ".idea": _EDITOR_STATE,
    ".vscode": _EDITOR_STATE,
    "build": _BUILD_OUTPUT,
    "dist": _BUILD_OUTPUT,
    "coverage": _COVERAGE_REPORT,
    "htmlcov": _COVERAGE_REPORT,
}

# An egg-info directory carries the distribution name, so it can never be
# matched by equality. It was listed above as the glob `*.egg-info` in a set
# that only ever compared whole path segments, which matched nothing at all --
# the kind of exclusion that looks present in review and does nothing at run
# time, and the reason each of these now has to produce a count.
EGG_INFO = ".egg-info"

# Machine-written files that do carry a supported extension, so the extension
# table alone would send them to a specialist. Reviewing a bundle spends a
# module's budget on a file nobody can edit.
MINIFIED_SUFFIXES = (".min.js", ".min.mjs", ".min.jsx", ".bundle.js", "-min.js")

# Generated clients and stubs, by the two conventions that carry the fact in
# the name: a directory everything under is generated, or a filename suffix the
# generator stamps on.
GENERATED_DIRS = frozenset({"generated", "__generated__", ".generated"})
GENERATED_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", ".pb.go", "_pb.js", ".g.dart", ".gen.go")

# Test data. Whole segments again, and `testdata` is the name the Go toolchain
# itself refuses to compile.
FIXTURE_DIRS = frozenset({"fixtures", "__fixtures__", "testdata", "__snapshots__", "cassettes"})

# Files that hold live credentials for the repository under review. Refused by
# name, because refusing them by extension is not a decision anybody made: a
# `.env` has no suffix `EXTENSIONS` claims, so today it survives on a table
# written to answer "which parser reads this?" that was never asked about
# secrets. One more entry there and a production key is in a prompt, and from
# there in a cassette that gets committed.
SECRET_FILENAMES = frozenset({".env", ".envrc"})

# The committed half of the same convention. A template names the variables and
# holds none of the values, so it is safe, and it is worth reading: a pool size
# declared here against a worker count declared in the Dockerfile is exactly
# the relationship a reviewer shown one file at a time cannot see.
ENV_TEMPLATES = frozenset({".env.example", ".env.sample"})


def holds_live_secrets(name: str) -> bool:
    """Whether a file of this name must never be opened.

    Matched on the whole filename rather than on a suffix, so `.env.local` and
    `.env.production` -- which is what a real service actually ships -- are
    refused alongside the bare name, while `environment.py` is not.

    Public because this mapper is not the only reader in the system. Symbol
    location resolves whatever repo-relative path a model names, and that path
    is a model's output rather than ours.
    """
    if name in ENV_TEMPLATES:
        return False
    return name in SECRET_FILENAMES or name.startswith(".env.") or name.endswith(".env")


def _not_source(relative: Path) -> tuple[str, str] | None:
    """The category and reason this file stays out of the map, or None.

    Directories are read outermost first, so the answer names the tree a
    reader would recognise: a file under `node_modules/x/build/` is reported
    as node_modules, which is the thing they would delete.
    """
    for part in relative.parts[:-1]:
        if part in EXCLUDED_DIRS:
            return part, EXCLUDED_DIRS[part]
        if part.endswith(EGG_INFO):
            return "egg-info", _BUILD_OUTPUT
        if part in GENERATED_DIRS:
            return "generated", _GENERATED
        if part in FIXTURE_DIRS:
            return "fixtures", _FIXTURES

    name = relative.name
    if name.endswith(MINIFIED_SUFFIXES):
        return "minified", _MINIFIED
    if name.endswith(GENERATED_SUFFIXES):
        return "generated", _GENERATED
    if relative.suffix.lower() not in EXTENSIONS:
        return "unsupported", _UNSUPPORTED
    return None


# The extensions a path-relative specifier may name, in the order a resolver
# tries them. `.ts` first, because a `.js` specifier in a TypeScript project
# means the `.ts` file far more often than it means a real `.js` one.
SCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


class Cartographer:
    """Builds a `RepoMap` from a repository root."""

    def __init__(
        self,
        root: Path,
        *,
        scope: tuple[str, ...] = (),
        entrypoints: tuple[str, ...] = (),
        include_tests: bool = False,
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
        self._include_tests = include_tests

    def map(self) -> RepoMap:
        found, excluded = self._walk()
        sources = sorted(found)
        if self._scope and not sources:
            raise ValueError(
                f"scope {list(self._scope)} matched no files under {self._root}. "
                "Reviewing nothing and reporting nothing reads as a clean bill of health."
            )
        index = self._index(sources)
        # Only files the map contains may be the target of an edge. Resolving
        # against the filesystem instead would draw edges to files the walk
        # excluded, which is how a review comes to report a dependency on
        # something it never read.
        known = {self._relative(source) for source in sources}

        nodes: list[ModuleNode] = []
        unparsed: list[str] = []
        skipped: dict[str, str] = {}
        churn = self._churn()

        for path in sources:
            rel = self._relative(path)

            if not self._include_tests and looks_like_a_test(rel):
                skipped[rel] = "a test rather than the service; --include-tests to review it"
                continue

            reason = self._refuse(path)
            if reason is not None:
                skipped[rel] = reason
                continue
            adapter = adapter_for(path)
            if adapter is None:  # unreachable: the walk filters by extension
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
                if (target := self._resolve_import(name, index, path, known)) is not None
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
            excluded=excluded,
            context=self._context(),
        )

    def _context(self) -> dict[str, str]:
        """Deployment configuration, trimmed.

        Only the named files: this is sent with every module, so anything here
        is paid for many times over and earns its place only by changing how
        the module reads. A .env is never collected -- context reaches a model
        and a committed recording, and a secret belongs in neither. Its
        committed template is, because it names the variables and holds none
        of them.
        """
        found: dict[str, str] = {}
        for name in CONTEXT_FILES:
            # The list above is edited by hand and `.env` is six keystrokes
            # from `.env.example`. Checking here rather than trusting the list
            # is what makes the refusal a rule instead of a convention.
            if holds_live_secrets(name):
                continue
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

        The credential check here is the second gate and should never fire:
        the walk already refuses these by name, and a file that reaches this
        point is only named, never opened. Being named in `skipped` is how a
        broken first gate becomes visible rather than silent.
        """
        if holds_live_secrets(path.name):
            return "holds live credentials and is never read"
        if path.is_symlink():
            return "symlink"
        if path.stat().st_size > MAX_SOURCE_BYTES:
            return "larger than the source size cap"
        return None

    # -- traversal ---------------------------------------------------------

    def _walk(self) -> tuple[list[Path], dict[str, Exclusion]]:
        """Every source file, and a tally of everything left behind.

        One pass, deliberately. The counts have to come from the same walk
        that builds the map, because a second walk is a second estimate of the
        first, and a number nobody measured is the thing this tool exists not
        to produce.
        """
        sources: list[Path] = []
        tally: Counter[tuple[str, str]] = Counter()

        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self._root)

            # Ordered by which answer a reader most needs. A secret is
            # reported as a secret wherever it sits, including inside a
            # vendored tree. A scoped run then leads with the scope, because
            # "you asked for backend/ only" explains more of the gap than any
            # category found inside what it hid.
            left_out: tuple[str, str] | None
            if holds_live_secrets(relative.name):
                left_out = ("secrets", _SECRETS)
            elif not self._in_scope(relative):
                left_out = ("out_of_scope", _OUT_OF_SCOPE)
            else:
                left_out = _not_source(relative)

            if left_out is not None:
                tally[left_out] += 1
                continue
            sources.append(path)

        # Largest first: at scale the top line is most of the repository, and
        # it is the line that decides whether the review was worth reading.
        return sources, {
            category: Exclusion(reason=reason, count=count)
            for (category, reason), count in sorted(
                tally.items(), key=lambda item: (-item[1], item[0][0])
            )
        }

    def _in_scope(self, relative: Path) -> bool:
        if not self._scope:
            return True
        posix = relative.as_posix()
        return any(posix == part or posix.startswith(f"{part}/") for part in self._scope)

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

    def _resolve_import(
        self, specifier: str, index: dict[str, str], source: Path, known: set[str]
    ) -> str | None:
        """One import, resolved by whichever rule its language uses.

        A specifier beginning with a dot is a path relative to the importing
        file, which is how TypeScript, JavaScript and their variants name a
        sibling module. Everything else is a dotted name, which is Python's
        rule and the one this resolver was originally written for.
        """
        if specifier.startswith("."):
            return self._resolve_beside(specifier, source, known)
        return self._resolve(specifier, index)

    def _resolve_beside(self, specifier: str, source: Path, known: set[str]) -> str | None:
        """A path-relative specifier, resolved the way a bundler would.

        The extension in the specifier is discarded before searching. Under
        ESM, TypeScript requires `./db.js` to name `db.ts`: the specifier
        describes the file that will exist after compilation, not the one on
        disk. Trusting it literally finds nothing in any TypeScript repository
        written to the standard the compiler enforces.

        normpath rather than resolve, so a symlink cannot walk the target out
        of the repository being reviewed.
        """
        target = Path(os.path.normpath(source.parent / specifier))
        stem = target.with_suffix("") if target.suffix in SCRIPT_SUFFIXES else target

        for suffix in SCRIPT_SUFFIXES:
            candidate = self._relative(stem.with_name(stem.name + suffix))
            if candidate in known:
                return candidate

        # A directory names the index file inside it.
        for suffix in SCRIPT_SUFFIXES:
            candidate = self._relative(stem / f"index{suffix}")
            if candidate in known:
                return candidate

        return None

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
