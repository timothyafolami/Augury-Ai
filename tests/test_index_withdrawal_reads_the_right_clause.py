"""Withdrawing a true index claim is worse than leaving a false one in.

This module's guarantee is "Only withdraws. A column this cannot prove indexed
is left alone." Two constructions broke it, and both are common rather than
contrived.

A bystander identifier: `covering` accepts any indexed (table, column) whose
two names appear anywhere in the mechanism. `id` appears in essentially every
migration and in most prose about a query, so a claim that `status` has no
index was withdrawn because `orders.id` is indexed -- with a reason that is
true about a column the finding never mentioned.

A composite index, exploded per column: a two-column index on
(user_id, created_at) was recorded as indexing `created_at` on its own, which
it does not, so a true claim about scanning on `created_at` was withdrawn.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.indexes import indexed_columns, withdraw_false_index_claims
from augury.core.schema.model import Operation


def _finding(mechanism: str) -> Finding:
    return Finding(
        path="app/api.py",
        line=1,
        layer="data",
        symbol="list_orders",
        mechanism=mechanism,
        remediation="Add an index.",
        severity=Severity.HIGH,
    )


def _op(kind: str, table: str, columns: tuple[str, ...]) -> Operation:
    return Operation(kind=kind, table=table, columns=columns, path="m.py", line=1)


def test_an_index_on_a_column_the_claim_never_mentions_does_not_withdraw_it() -> None:
    indexed = indexed_columns((_op("create_unique_constraint", "orders", ("id",)),))

    kept, withdrawn = withdraw_false_index_claims(
        [
            _finding(
                "list_orders joins orders on id and then filters on status, "
                "a column with no index, so every page scan is sequential."
            )
        ],
        indexed,
    )

    assert len(kept) == 1, f"withdrawn as: {withdrawn[0].reason if withdrawn else ''}"


def test_a_composite_index_does_not_prove_its_trailing_column_indexed() -> None:
    """A composite cannot serve a predicate on a non-leading column alone."""
    indexed = indexed_columns((_op("create_index", "events", ("user_id", "created_at")),))

    kept, _ = withdraw_false_index_claims(
        [
            _finding(
                "The dashboard groups events by created_at with no index on "
                "that column, so the query scans the table."
            )
        ],
        indexed,
    )

    assert len(kept) == 1


def test_a_composite_index_still_settles_a_claim_about_its_leading_column() -> None:
    """It does serve that one, so the withdrawal is right there."""
    indexed = indexed_columns((_op("create_index", "events", ("user_id", "created_at")),))

    _, withdrawn = withdraw_false_index_claims(
        [_finding("The query filters events by user_id with no index, so it scans.")],
        indexed,
    )

    assert len(withdrawn) == 1


def test_a_genuinely_false_claim_is_still_withdrawn() -> None:
    """The behaviour this exists for, which the fix must not cost."""
    indexed = indexed_columns((_op("create_index", "orders", ("status",)),))

    _, withdrawn = withdraw_false_index_claims(
        [_finding("list_orders filters orders on status, which has no index, so it scans.")],
        indexed,
    )

    assert len(withdrawn) == 1
