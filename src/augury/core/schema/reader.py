"""Reading `op.*` calls out of alembic migrations, without importing them.

Parsed rather than executed: a migration imports the application, and importing
a repository under review is the one thing a reviewer must never do.
"""

from __future__ import annotations

import ast
from pathlib import Path

from augury.core.schema.model import Operation

MIGRATION_DIRS = ("alembic/versions", "migrations/versions", "migrations")

# The calls that change a table that may already hold rows.
INTERESTING = frozenset(
    {
        "add_column",
        "drop_column",
        "alter_column",
        "create_index",
        "drop_index",
        "create_foreign_key",
        "create_table",
        "drop_table",
        "create_unique_constraint",
        "create_check_constraint",
    }
)


def read_migrations(root: Path) -> tuple[Operation, ...]:
    """Every schema operation the repository's migrations declare, in order."""
    found: list[Operation] = []
    for directory in MIGRATION_DIRS:
        base = Path(root) / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            found.extend(_operations_in(path, root))
    return tuple(found)


def _operations_in(path: Path, root: Path) -> list[Operation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError, RecursionError):
        return []

    relative = path.relative_to(root).as_posix()
    forward = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    if forward is None:
        return []

    # Only the forward migration. A downgrade drops the column its upgrade
    # added, which is what a downgrade is -- and reading both reported one
    # dropped-column finding per migration on the first real repository this
    # ran against, 34 of them, every one wrong.
    found: list[Operation] = []
    for node in ast.walk(forward):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name not in INTERESTING:
            continue
        found.append(
            Operation(
                kind=name,
                table=_table(name, node),
                columns=tuple(_columns(name, node)),
                path=relative,
                line=node.lineno,
                keywords=_keywords(node),
            )
        )
    return found


# Where the table name sits in each call's positional arguments. `create_index`
# and `create_foreign_key` both take the constraint's own name first, so reading
# argument zero gives the index rather than the table it is built on.
_TABLE_POSITION = {"create_index": 1, "create_foreign_key": 1, "drop_index": 1}


def _table(kind: str, node: ast.Call) -> str:
    return _string_at(node.args, _TABLE_POSITION.get(kind, 0))


def _keywords(node: ast.Call) -> dict[str, str]:
    """Keywords on this call, and on any call nested in its arguments.

    `op.add_column('t', sa.Column('c', sa.Text(), nullable=False))` carries the
    keyword that matters on the inner call, not the outer one.
    """
    collected = {kw.arg: _literal(kw.value) for kw in node.keywords if kw.arg is not None}
    for argument in node.args:
        if isinstance(argument, ast.Call):
            for kw in argument.keywords:
                if kw.arg is not None:
                    collected.setdefault(kw.arg, _literal(kw.value))
    return collected


def _columns(kind: str, node: ast.Call) -> list[str]:
    """The columns an operation touches, wherever that grammar puts them."""
    if kind == "add_column":
        # op.add_column('table', sa.Column('name', ...))
        for argument in node.args[1:]:
            if isinstance(argument, ast.Call):
                return [_first_string(argument.args)]
        return []
    if kind == "drop_column":
        return [s for s in (_string_at(node.args, 1),) if s]
    if kind == "create_index":
        # op.create_index('name', 'table', ['a', 'b'])
        return _string_list(node.args, 2)
    if kind == "create_foreign_key":
        # op.create_foreign_key('name', 'source', 'target', ['local'], ['remote'])
        return _string_list(node.args, 3)
    return []


def _first_string(args: list[ast.expr]) -> str:
    for argument in args:
        value = _literal(argument)
        if value:
            return value
    return ""


def _string_at(args: list[ast.expr], index: int) -> str:
    return _literal(args[index]) if len(args) > index else ""


def _string_list(args: list[ast.expr], index: int) -> list[str]:
    if len(args) <= index:
        return []
    node = args[index]
    if not isinstance(node, ast.List | ast.Tuple):
        return []
    return [value for element in node.elts if (value := _literal(element))]


def _literal(node: ast.expr) -> str:
    """A string constant, or the source of anything else, as written.

    `op.f('ix_users_email')` and a bare string both name an index, and the
    caller wants the name in either spelling.
    """
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Call):
        return _first_string(node.args)
    return ast.unparse(node)
