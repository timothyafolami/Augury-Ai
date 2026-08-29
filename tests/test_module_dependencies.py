"""Which third-party packages a module actually uses.

A specialist asked about SQLAlchemy session handling answers from its training
cutoff. The repository pins a version, the registry knows what that version is,
and the module says which packages it imports -- so the specialist can be told
"this file uses SQLAlchemy 2.0.20, and 2.0.36 is current" instead of guessing
which defaults apply.

Only the packages this module imports. Handing every specialist all thirty-four
of a service's dependencies is noise priced per call.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.cartography import Cartographer


def _module(root: Path, path: str):  # type: ignore[no-untyped-def]
    return next(m for m in Cartographer(root).map().modules if m.path == path)


def test_third_party_imports_are_kept(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "import sqlalchemy\nimport httpx\nfrom celery import Celery\n\n\ndef f():\n    pass\n"
    )

    assert set(_module(tmp_path, "app.py").external) == {"sqlalchemy", "httpx", "celery"}


def test_a_module_in_this_repository_is_not_third_party(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "db.py").write_text("import sqlalchemy\n")
    (tmp_path / "app" / "api.py").write_text("from app import db\nimport httpx\n")

    external = set(_module(tmp_path, "app/api.py").external)

    assert external == {"httpx"}
    assert "app" not in external
    assert "db" not in external


def test_the_standard_library_is_not_a_dependency(tmp_path: Path) -> None:
    """`os` has no version to be behind on."""
    (tmp_path / "app.py").write_text("import os\nimport json\nimport httpx\n")

    assert set(_module(tmp_path, "app.py").external) == {"httpx"}


def test_a_recognised_package_is_kept_even_though_it_matched_a_signal(
    tmp_path: Path,
) -> None:
    """`sqlalchemy` maps to the data signal, and it is still a dependency.

    Only unrecognised imports used to survive, so every package the signal
    tables knew about -- which is every package worth asking about -- was
    dropped before anything could look up its version.
    """
    (tmp_path / "app.py").write_text("import sqlalchemy\n")

    assert "sqlalchemy" in _module(tmp_path, "app.py").external
