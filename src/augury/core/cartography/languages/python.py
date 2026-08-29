"""The Python adapter, on the standard library rather than tree-sitter.

Python keeps a native `ast` adapter because the source-level detectors in
`source_signals` need real Python semantics -- which exception types are broad,
whether a handler re-raises -- and because it makes the common case free of a
parser dependency.
"""

from __future__ import annotations

import ast
import sys

from augury.core.cartography.languages.base import (
    Language,
    LanguageAdapter,
    ParsedModule,
    ParseError,
)
from augury.core.cartography.model import Signal
from augury.core.cartography.signals import is_inert, signals_for_import
from augury.core.cartography.source_signals import signals_from_source


class PythonAdapter(LanguageAdapter):
    """Parses Python and reports its imports and layer signals."""

    @property
    def language(self) -> Language:
        return Language.PYTHON

    def parse(self, source: str, *, package: str) -> ParsedModule:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ParseError(str(exc)) from exc

        imports: set[str] = set()
        signals: set[Signal] = signals_from_source(tree)
        unmatched: set[str] = set()
        third_party: set[str] = set()

        for node in ast.walk(tree):
            for dotted in _imported_names(node, package):
                imports.add(dotted)
                top_level = dotted.split(".")[0]
                # `is_inert` answers "has this no concern to review", which is
                # a different question: `os` is not inert because it carries a
                # security signal, and it is still not a dependency. The
                # interpreter knows its own standard library.
                if top_level not in sys.stdlib_module_names:
                    third_party.add(top_level)
                matched = signals_for_import(top_level)
                if matched:
                    signals |= matched
                elif not is_inert(top_level):
                    unmatched.add(top_level)

        return ParsedModule(
            loc=sum(1 for line in source.splitlines() if line.strip()),
            imports=frozenset(imports),
            # Modules named by string rather than by `import`. Celery's
            # `include=[...]`, `import_module(name)` and Django's
            # INSTALLED_APPS are all edges an import graph built from import
            # statements cannot see -- on a real Celery service that was its
            # entire task layer, reported as code no request reaches.
            named_in_strings=frozenset(_dotted_strings(tree)),
            third_party=frozenset(third_party),
            signals=frozenset(signals),
            unmatched_imports=frozenset(unmatched),
        )


def _imported_names(node: ast.AST, package: str) -> list[str]:
    """Every dotted name this statement could be depending on.

    `from pkg import store` is listed as `pkg.store` before `pkg`, so the
    submodule is preferred when one exists and the package is used only when
    the imported name is not a module.
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


# A string has to look like a module path before it is worth resolving: at
# least one dot, and every segment a plain identifier.
_MIN_SEGMENTS = 2


def _dotted_strings(tree: ast.Module) -> set[str]:
    """Every string constant that could name a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        candidate = node.value.strip()
        segments = candidate.split(".")
        if len(segments) < _MIN_SEGMENTS:
            continue
        if all(segment.isidentifier() for segment in segments):
            found.add(candidate)
    return found
