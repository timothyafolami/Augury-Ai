"""A claim about an index is checkable, so it should be checked.

On a real repository the reviewer reported that `admin_login` queries the users
table "without an index" on email, and predicted a 250ms p99 against a table it
described as having roughly a million rows. Both halves were invented: the
model was shown one route handler, and `index=True` is in the model file with
`ix_users_email` in the initial migration.

The specialist cannot see those files. The harness has already parsed them,
which makes this the same shape as the falsifiability gate: a claim the code
can settle should not reach a human as an open question.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.indexes import IndexedColumns, withdraw_false_index_claims


def _finding(mechanism: str, remediation: str = "Add the missing index.") -> Finding:
    return Finding(
        path="app/api/routes/admin.py",
        line=37,
        layer="data",
        symbol="admin_login",
        mechanism=mechanism,
        severity=Severity.HIGH,
        remediation=remediation,
    )


INDEXED = IndexedColumns({("users", "email"), ("admins", "email")})


def test_a_missing_index_claim_about_an_indexed_column_is_withdrawn() -> None:
    finding = _finding(
        "The login endpoint queries the users table by email without an index, "
        "causing a full table scan."
    )

    kept, withdrawn = withdraw_false_index_claims([finding], INDEXED)

    assert kept == []
    assert withdrawn[0].reason.startswith("users.email is indexed")


def test_a_missing_index_claim_about_an_unindexed_column_survives() -> None:
    finding = _finding(
        "The endpoint filters the sessions table by tenant_id without an index, "
        "causing a full table scan."
    )

    kept, withdrawn = withdraw_false_index_claims([finding], INDEXED)

    assert len(kept) == 1
    assert withdrawn == []


def test_a_finding_that_is_not_about_an_index_is_untouched() -> None:
    finding = _finding("A blocking Stripe call inside an async function stalls the loop.")

    kept, withdrawn = withdraw_false_index_claims([finding], INDEXED)

    assert len(kept) == 1
    assert withdrawn == []


def test_nothing_is_withdrawn_when_no_migrations_were_read() -> None:
    """Knowing no indexes is not the same as knowing there are none."""
    finding = _finding("Queries the users table by email without an index.")

    kept, withdrawn = withdraw_false_index_claims([finding], IndexedColumns(set()))

    assert len(kept) == 1
    assert withdrawn == []


def test_indexes_are_read_from_the_migrations(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from augury.core.indexes import indexed_columns
    from augury.core.schema import read_migrations

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n\n"
        "def upgrade():\n"
        "    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)\n"
    )

    assert ("users", "email") in indexed_columns(read_migrations(tmp_path))
