"""Reading the migrations as a schema, not as thirty-four more modules.

A migration's defects are not in the file. They are in what the statement does
to a table that already has rows, and to the queries running against it while
it runs. No per-file review reaches that, because the file is four lines long
and every line is correct.

Every check here is deterministic. These are facts about DDL, not judgements,
and asking a model to restate them would cost money to get them right slightly
less often.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.schema import read_migrations, schema_findings


def _write(tmp_path: Path, name: str, body: str) -> Path:
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    (versions / name).write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n\ndef upgrade():\n" + body
    )
    return tmp_path


def _find(tmp_path: Path) -> list[str]:
    return [f.rule for f in schema_findings(read_migrations(tmp_path))]


def test_a_not_null_column_with_no_default_is_reported(tmp_path: Path) -> None:
    """Postgres rejects this outright on a table that already has rows."""
    _write(
        tmp_path,
        "0001_add.py",
        "    op.add_column('users', sa.Column('email', sa.Text(), nullable=False))\n",
    )
    assert "not-null-without-default" in _find(tmp_path)


def test_a_not_null_column_with_a_server_default_is_fine(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0002_add.py",
        "    op.add_column('users', sa.Column('email', sa.Text(), nullable=False,"
        " server_default=''))\n",
    )
    assert "not-null-without-default" not in _find(tmp_path)


def test_a_nullable_column_is_fine(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0003_add.py",
        "    op.add_column('users', sa.Column('email', sa.Text(), nullable=True))\n",
    )
    assert _find(tmp_path) == []


def test_an_index_built_without_concurrently_is_reported(tmp_path: Path) -> None:
    """CREATE INDEX takes a lock that blocks writes for the whole build."""
    _write(
        tmp_path,
        "0004_index.py",
        "    op.create_index('ix_users_email', 'users', ['email'], unique=False)\n",
    )
    assert "index-blocks-writes" in _find(tmp_path)


def test_a_concurrent_index_is_fine(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0005_index.py",
        "    op.create_index('ix_users_email', 'users', ['email'], postgresql_concurrently=True)\n",
    )
    assert "index-blocks-writes" not in _find(tmp_path)


def test_an_index_created_inside_create_table_is_fine(tmp_path: Path) -> None:
    """A table created in the same migration has no rows and no readers."""
    _write(
        tmp_path,
        "0006_new.py",
        "    op.create_table('events', sa.Column('id', sa.Integer()))\n"
        "    op.create_index('ix_events_id', 'events', ['id'])\n",
    )
    assert "index-blocks-writes" not in _find(tmp_path)


def test_a_foreign_key_with_no_index_is_reported(tmp_path: Path) -> None:
    """Every cascade and every parent delete scans the child table without one."""
    _write(
        tmp_path,
        "0007_fk.py",
        "    op.create_foreign_key('fk_o_u', 'orders', 'users', ['user_id'], ['id'])\n",
    )
    assert "foreign-key-without-index" in _find(tmp_path)


def test_a_foreign_key_that_is_indexed_is_fine(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0008_fk.py",
        "    op.create_foreign_key('fk_o_u', 'orders', 'users', ['user_id'], ['id'])\n"
        "    op.create_index('ix_orders_user_id', 'orders', ['user_id'])\n",
    )
    assert "foreign-key-without-index" not in _find(tmp_path)


def test_a_dropped_column_is_reported(tmp_path: Path) -> None:
    """Old code still selects it for as long as the rolling deploy takes."""
    _write(tmp_path, "0009_drop.py", "    op.drop_column('users', 'legacy')\n")
    assert "column-dropped-in-one-step" in _find(tmp_path)


def test_a_repository_with_no_migrations_yields_nothing(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    assert read_migrations(tmp_path) == ()
    assert schema_findings(()) == ()


def test_a_finding_names_the_migration_it_came_from(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0010_add.py",
        "    op.add_column('users', sa.Column('x', sa.Text(), nullable=False))\n",
    )
    finding = schema_findings(read_migrations(tmp_path))[0]

    assert finding.path.endswith("0010_add.py")
    assert finding.line > 0
    assert "users" in finding.detail


def test_only_the_forward_migration_is_checked(tmp_path: Path) -> None:
    """A downgrade drops the column it added. That is what a downgrade is.

    Read without this distinction, every alembic repository reports one
    dropped-column finding per migration -- 34 of them on the first real
    repository this ran against, all of them wrong.
    """
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0011_pair.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n\n\n"
        "def upgrade():\n"
        "    op.add_column('users', sa.Column('nickname', sa.Text(), nullable=True))\n\n\n"
        "def downgrade():\n"
        "    op.drop_column('users', 'nickname')\n"
    )

    assert schema_findings(read_migrations(tmp_path)) == ()


def test_a_drop_in_the_forward_migration_is_still_reported(tmp_path: Path) -> None:
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0012_drop.py").write_text(
        "from alembic import op\n\n\ndef upgrade():\n    op.drop_column('users', 'legacy')\n"
    )

    assert [f.rule for f in schema_findings(read_migrations(tmp_path))] == [
        "column-dropped-in-one-step"
    ]


def test_a_table_created_by_an_earlier_migration_is_not_new(tmp_path: Path) -> None:
    """Freshness is per migration, not per repository.

    A table created in migration 1 has rows by migration 34. Treating it as new
    for the life of the project silences every finding about it -- which is why
    this reported nothing at all on a repository whose migrations add a NOT
    NULL column to a table created eight migrations earlier.
    """
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_create.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n\n"
        "def upgrade():\n    op.create_table('users', sa.Column('id', sa.Integer()))\n"
    )
    (versions / "0002_later.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n\n"
        "def upgrade():\n"
        "    op.add_column('users', sa.Column('email', sa.Text(), nullable=False))\n"
        "    op.create_index('ix_users_email', 'users', ['email'])\n"
    )

    rules = {f.rule for f in schema_findings(read_migrations(tmp_path))}

    assert "not-null-without-default" in rules
    assert "index-blocks-writes" in rules
