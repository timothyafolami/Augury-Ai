"""What the migrations do that a table with rows will not survive.

Each rule is a fact about DDL rather than a judgement, which is why none of
them costs a model call. Each names the remediation, because a finding that
does not is a complaint.
"""

from __future__ import annotations

from augury.core.schema.model import Operation, SchemaFinding


def schema_findings(operations: tuple[Operation, ...]) -> tuple[SchemaFinding, ...]:
    """Every deterministic defect these operations carry."""
    # A table is new only within the migration that creates it. It has rows by
    # the next one, and treating it as new for the life of the project silences
    # every finding about it -- which reported zero findings on a real
    # repository that adds a NOT NULL column to a table created earlier.
    fresh_in: dict[str, set[str]] = {}
    for op in operations:
        if op.kind == "create_table":
            fresh_in.setdefault(op.path, set()).add(op.table)

    # An index anywhere in the migration history covers a foreign key, whenever
    # it was added.
    indexed = {
        (op.table, column)
        for op in operations
        if op.kind == "create_index"
        for column in op.columns
    }

    found: list[SchemaFinding] = []
    for op in operations:
        found.extend(_check(op, fresh=fresh_in.get(op.path, set()), indexed=indexed))
    return tuple(found)


def _check(op: Operation, *, fresh: set[str], indexed: set[tuple[str, str]]) -> list[SchemaFinding]:
    # The nullable keyword lives on the nested Column, not on add_column; the
    # reader collects from both.
    adds_not_null = (
        op.kind == "add_column"
        and op.table not in fresh
        and op.keywords.get("nullable") == "False"
        and not _has_default(op)
    )
    if adds_not_null:
        return [
            SchemaFinding(
                rule="not-null-without-default",
                path=op.path,
                line=op.line,
                detail=(
                    f"adds a NOT NULL column to `{op.table}`, which already has "
                    "rows, with no server default. Postgres rejects this outright"
                ),
                remediation=(
                    "Add it nullable, backfill, then set NOT NULL in a later "
                    "migration; or give it a server_default"
                ),
            )
        ]

    builds_blocking_index = (
        op.kind == "create_index"
        and op.table not in fresh
        and "True" not in op.keywords.get("postgresql_concurrently", "")
    )
    if builds_blocking_index:
        return [
            SchemaFinding(
                rule="index-blocks-writes",
                path=op.path,
                line=op.line,
                detail=(
                    f"builds an index on `{op.table}` without CONCURRENTLY, taking a "
                    "lock that blocks every write to the table until it finishes"
                ),
                remediation=(
                    "postgresql_concurrently=True, with the migration outside a "
                    "transaction, since CONCURRENTLY cannot run inside one"
                ),
            )
        ]

    if op.kind == "create_foreign_key":
        missing = [c for c in op.columns if (op.table, c) not in indexed]
        if missing:
            return [
                SchemaFinding(
                    rule="foreign-key-without-index",
                    path=op.path,
                    line=op.line,
                    detail=(
                        f"`{op.table}.{missing[0]}` references another table with no index "
                        "on it, so every delete of a parent row scans this table"
                    ),
                    remediation=f"Create an index on `{op.table}.{missing[0]}`",
                )
            ]

    if op.kind == "drop_column":
        column = op.columns[0] if op.columns else "a column"
        return [
            SchemaFinding(
                rule="column-dropped-in-one-step",
                path=op.path,
                line=op.line,
                detail=(
                    f"drops `{op.table}.{column}` in one step. During a rolling deploy the "
                    "previous version is still selecting it"
                ),
                remediation=("Stop reading it, deploy, then drop it in a later migration"),
            )
        ]

    return []


def _has_default(op: Operation) -> bool:
    return any("default" in key for key in op.keywords)
