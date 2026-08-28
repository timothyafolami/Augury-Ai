"""Signals that no import table can see.

An import tells you a module *could* touch a concern. These detectors tell you
it *does*, for three defect classes whose whole danger is that they look
ordinary: a swallowed exception, a query built by string interpolation, and
shared mutable state. All three are Tier-1 entries in the defect taxonomy and
none of them has a distinctive import.

Deliberately conservative. A false signal costs a real model call, and a
reviewer that flags correct code trains its user to ignore it.
"""

from __future__ import annotations

import ast

from augury.core.cartography.model import Signal

_BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})

# Pairs rather than single words, matched case-sensitively. SQL in source is
# conventionally uppercase; English prose is not. Matching " from " loosely
# flagged every log line of the form f"downloaded {n} bytes from {url}".
_SQL_SHAPES = (
    ("SELECT", "FROM"),
    ("INSERT", "INTO"),
    ("UPDATE", "SET"),
    ("DELETE", "FROM"),
)

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler)


def signals_from_source(tree: ast.Module) -> set[Signal]:
    """Concerns evidenced by the shape of the code rather than its imports."""
    signals: set[Signal] = set()

    for node in ast.walk(tree):
        if _swallows_an_exception(node):
            signals.add(Signal.CRAFT)
        elif _builds_a_query_by_interpolation(node):
            signals |= {Signal.SECURITY, Signal.DATA}
        elif isinstance(node, ast.Global):
            signals.add(Signal.CONCURRENCY)

    return signals


# -- swallowed exceptions --------------------------------------------------


def _swallows_an_exception(node: ast.AST) -> bool:
    """A broad handler that never re-raises turns a failure into a plausible
    answer. Narrow handlers, and any handler that re-raises, are correct."""
    if not isinstance(node, ast.ExceptHandler):
        return False
    if not _is_broad(node.type):
        return False
    return not any(
        _reraises(statement) for statement in node.body if not isinstance(statement, _NESTED_SCOPES)
    )


def _is_broad(exception_type: ast.expr | None) -> bool:
    """Bare, `Exception`, `pkg.Exception`, or a tuple containing any of those."""
    if exception_type is None:  # bare `except:`
        return True
    if isinstance(exception_type, ast.Tuple):
        return any(_is_broad(element) for element in exception_type.elts)
    if isinstance(exception_type, ast.Name):
        return exception_type.id in _BROAD_EXCEPTIONS
    if isinstance(exception_type, ast.Attribute):
        return exception_type.attr in _BROAD_EXCEPTIONS
    return False


def _reraises(node: ast.AST) -> bool:
    """A `raise` reachable from this handler's own body.

    Nested scopes do not count: a helper function defined in the handler may
    never be called, and an inner handler re-raising a different error still
    loses the original failure.
    """
    if isinstance(node, ast.Raise):
        return True
    return any(
        _reraises(child)
        for child in ast.iter_child_nodes(node)
        if not isinstance(child, _NESTED_SCOPES)
    )


# -- interpolated queries --------------------------------------------------


def _builds_a_query_by_interpolation(node: ast.AST) -> bool:
    """f-strings, %-formatting, .format() and concatenation carrying SQL.
    Parameterised queries are plain constants and are correctly ignored."""
    if isinstance(node, ast.JoinedStr):
        return _looks_like_sql(_literal_parts(node))

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
        return any(_is_sql_constant(side) for side in (node.left, node.right))

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "format" and _is_sql_constant(node.func.value)

    return False


def _literal_parts(node: ast.JoinedStr) -> str:
    return "".join(
        part.value
        for part in node.values
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
    )


def _is_sql_constant(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _looks_like_sql(node.value)
    )


def _looks_like_sql(text: str) -> bool:
    """Two co-occurring uppercase keywords, so prose cannot trip it."""
    return any(all(word in text for word in shape) for shape in _SQL_SHAPES)
