"""A test file is not the service, and reviewing it as one costs money.

A full-coverage run spent tokens on `test_password_reset_flow.py`, asking eight
production concerns of a file that never serves a request. On a real backend
that is 20 of 167 modules and 4,280 lines: 12% of a review, producing findings
about code whose failure mode is a red build rather than an incident.

Excluded by default and included on request, because a test suite does have
defects worth finding -- a test that asserts on a mock, one that cannot fail --
and those are a different review with a different brief.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.cartography import Cartographer

TEST_PATHS = [
    "tests/test_auth.py",
    "backend/tests/test_cache.py",
    "src/__tests__/api.test.ts",
    "spec/models_spec.py",
    "app/user_test.go",
    "conftest.py",
    "run_pipeline_test.py",
]

PRODUCTION_PATHS = [
    "app/api/routes/auth.py",
    "src/services/latest.py",
    "app/contest/rules.py",
    "app/protest.py",
]


def _map(tmp_path: Path, paths: list[str], **kwargs: object):  # type: ignore[no-untyped-def]
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("import sqlalchemy\n\n\ndef f():\n    return sqlalchemy\n")
    return Cartographer(tmp_path, **kwargs).map()  # type: ignore[arg-type]


@pytest.mark.parametrize("path", TEST_PATHS)
def test_a_test_file_is_not_reviewed_by_default(tmp_path: Path, path: str) -> None:
    mapped = _map(tmp_path, [path, "app/main.py"])

    assert {m.path for m in mapped.modules} == {"app/main.py"}


@pytest.mark.parametrize("path", PRODUCTION_PATHS)
def test_a_production_file_whose_name_contains_test_is_kept(tmp_path: Path, path: str) -> None:
    """`latest.py`, `contest/`, `protest.py`. A substring match would eat these."""
    mapped = _map(tmp_path, [path])

    assert {m.path for m in mapped.modules} == {path}


def test_tests_can_be_asked_for(tmp_path: Path) -> None:
    """They have their own defects; they are a different review."""
    mapped = _map(tmp_path, ["tests/test_auth.py", "app/main.py"], include_tests=True)

    assert "tests/test_auth.py" in {m.path for m in mapped.modules}


def test_the_map_says_how_many_it_left_out(tmp_path: Path) -> None:
    """Silently skipping a fifth of a repository reads as a clean bill."""
    mapped = _map(tmp_path, ["tests/test_auth.py", "tests/test_db.py", "app/main.py"])

    assert sum(1 for why in mapped.skipped.values() if "test" in why) == 2
