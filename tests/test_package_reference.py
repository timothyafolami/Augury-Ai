"""What the repository pins, against what the ecosystem currently ships.

A model's knowledge of a library ends at its training cutoff. The repository
under review pins exact versions, and the registry knows what those versions
are today -- so the gap between them is a fact neither the model nor the
reviewer has to guess at.

That gap is worth reporting on its own. A service pinned three majors behind
the library whose defaults it relies on is a finding, and it is one no amount
of reading the source will produce.

No test here touches the network. The fetcher is injected, because a test suite
that needs the internet is one that fails on a train.
"""

from __future__ import annotations

import json
from pathlib import Path

from augury.core.reference import PackageFacts, Registry, requirements_of

PYPI_SQLALCHEMY = {
    "info": {
        "name": "SQLAlchemy",
        "version": "2.0.36",
        "summary": "Database Abstraction Library",
        "yanked": False,
    },
    "releases": {"2.0.36": [{"upload_time_iso_8601": "2026-06-01T00:00:00Z"}]},
}


def _registry(payloads: dict[str, dict[str, object]] | None = None) -> Registry:
    served = payloads if payloads is not None else {"sqlalchemy": PYPI_SQLALCHEMY}

    def fetch(url: str) -> str | None:
        name = url.rstrip("/").split("/")[-2].lower()
        payload = served.get(name)
        return None if payload is None else json.dumps(payload)

    return Registry(fetch=fetch)


def test_a_requirements_file_is_read(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# comment\nSQLAlchemy==2.0.20\nfastapi>=0.100\n\n-r other.txt\ncelery\n"
    )

    pinned = requirements_of(tmp_path)

    assert pinned["sqlalchemy"] == "2.0.20"
    assert pinned["fastapi"] == "0.100"
    assert pinned["celery"] == ""


def test_a_pyproject_is_read(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["sqlalchemy>=2.0.36", "httpx==0.27.0"]\n'
    )

    pinned = requirements_of(tmp_path)

    assert pinned["sqlalchemy"] == "2.0.36"
    assert pinned["httpx"] == "0.27.0"


def test_the_registry_reports_what_is_current() -> None:
    facts = _registry().facts_for("sqlalchemy")

    assert facts is not None
    assert facts.latest == "2.0.36"
    assert "Database" in facts.summary


def test_a_package_the_registry_does_not_know_is_none() -> None:
    assert _registry({}).facts_for("not-a-real-package") is None


def test_the_registry_is_asked_once_per_package() -> None:
    calls: list[str] = []

    def fetch(url: str) -> str | None:
        calls.append(url)
        return json.dumps(PYPI_SQLALCHEMY)

    registry = Registry(fetch=fetch)
    registry.facts_for("sqlalchemy")
    registry.facts_for("sqlalchemy")

    assert len(calls) == 1


def test_a_registry_that_cannot_be_reached_degrades_to_nothing() -> None:
    """Offline is a normal state. A review must not need the internet."""

    def fetch(url: str) -> str | None:
        raise OSError("no network")

    assert Registry(fetch=fetch).facts_for("sqlalchemy") is None


def test_the_gap_between_pinned_and_current_is_reported() -> None:
    facts = PackageFacts(name="sqlalchemy", latest="2.0.36", summary="", released="2026-06-01")

    assert facts.behind("2.0.20") == "2.0.20 pinned, 2.0.36 current"
    assert facts.behind("2.0.36") is None
    assert facts.behind("") is None
