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
_SQL_KEYWORDS = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", " FROM ", " WHERE ")


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


def _swallows_an_exception(node: ast.AST) -> bool:
    """A broad handler that never re-raises turns a failure into a plausible
    answer. Narrow handlers, and any handler that re-raises, are correct."""
    if not isinstance(node, ast.ExceptHandler):
        return False
    if not _is_broad(node.type):
        return False
    return not any(isinstance(inner, ast.Raise) for inner in ast.walk(node))


def _is_broad(exception_type: ast.expr | None) -> bool:
    if exception_type is None:  # bare `except:`
        return True
    return isinstance(exception_type, ast.Name) and exception_type.id in _BROAD_EXCEPTIONS


def _builds_a_query_by_interpolation(node: ast.AST) -> bool:
    """f-strings and %-formatting carrying SQL. Parameterised queries are
    plain constants and are correctly ignored."""
    if isinstance(node, ast.JoinedStr):
        literal = "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ).upper()
        return _looks_like_sql(literal)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = node.left
        return isinstance(left, ast.Constant) and _looks_like_sql(str(left.value).upper())

    return False


def _looks_like_sql(text: str) -> bool:
    return any(keyword in text for keyword in _SQL_KEYWORDS)
