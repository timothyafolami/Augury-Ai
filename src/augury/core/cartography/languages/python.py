"""The Python adapter, on the standard library rather than tree-sitter.

Python keeps a native `ast` adapter because the source-level detectors in
`source_signals` need real Python semantics -- which exception types are broad,
whether a handler re-raises -- and because it makes the common case free of a
parser dependency.
"""

from __future__ import annotations

import ast

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

        for node in ast.walk(tree):
            for dotted in _imported_names(node, package):
                imports.add(dotted)
                top_level = dotted.split(".")[0]
                matched = signals_for_import(top_level)
                if matched:
                    signals |= matched
                elif not is_inert(top_level):
                    unmatched.add(top_level)

        return ParsedModule(
            loc=sum(1 for line in source.splitlines() if line.strip()),
            imports=frozenset(imports),
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
