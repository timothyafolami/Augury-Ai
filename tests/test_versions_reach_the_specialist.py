"""The specialist is told which versions it is looking at.

"SQLAlchemy sessions are not concurrency-safe" is a claim about a version. The
model answers from its training cutoff; the repository pins something; the
registry knows what is current. Handing the specialist all three costs nothing
per call and removes the guess.

Only the packages this module imports. Thirty-four dependencies in every
specialist prompt is noise priced per call.
"""

from __future__ import annotations

from augury.core.reference import PackageFacts
from augury.core.versions import describe_versions


class _Registry:
    def __init__(self, facts: dict[str, PackageFacts]) -> None:
        self._facts = facts

    def facts_for(self, name: str) -> PackageFacts | None:
        return self._facts.get(name)


REGISTRY = _Registry(
    {
        "sqlalchemy": PackageFacts(name="SQLAlchemy", latest="2.0.36", summary=""),
        "httpx": PackageFacts(name="httpx", latest="0.28.1", summary=""),
    }
)
PINNED = {"sqlalchemy": "2.0.20", "httpx": "0.28.1", "celery": "5.4.0"}


def test_only_the_packages_this_module_imports_are_described() -> None:
    text = describe_versions({"sqlalchemy"}, pinned=PINNED, registry=REGISTRY)

    assert "sqlalchemy" in text
    assert "httpx" not in text
    assert "celery" not in text


def test_the_pinned_version_and_the_current_one_are_both_given() -> None:
    text = describe_versions({"sqlalchemy"}, pinned=PINNED, registry=REGISTRY)

    assert "2.0.20" in text
    assert "2.0.36" in text


def test_a_package_that_is_current_says_so_without_a_second_number() -> None:
    text = describe_versions({"httpx"}, pinned=PINNED, registry=REGISTRY)

    assert "0.28.1" in text
    assert "current" in text


def test_a_package_the_registry_cannot_reach_still_reports_the_pin() -> None:
    """Offline, the pin is still worth knowing and the guess is still removed."""
    text = describe_versions({"celery"}, pinned=PINNED, registry=REGISTRY)

    assert "celery" in text
    assert "5.4.0" in text


def test_a_module_importing_nothing_third_party_says_so_rather_than_nothing() -> None:
    """An empty block in a prompt reads as a bug; a sentence reads as a fact."""
    text = describe_versions(set(), pinned=PINNED, registry=REGISTRY)

    assert "no third-party" in text.lower()


def test_an_unpinned_package_is_described_as_unpinned() -> None:
    text = describe_versions({"sqlalchemy"}, pinned={"sqlalchemy": ""}, registry=REGISTRY)

    assert "not pinned" in text


# -- not inventing versions ------------------------------------------------


def test_a_package_not_declared_by_this_repository_is_never_looked_up() -> None:
    """The worst failure available here is a fabricated version.

    A module importing the repository's own `src` package had it looked up on
    the registry, which happens to carry an unrelated package of that name, and
    the specialist was told "src: 0.0.7 current". That is invented context
    presented as fact, in the one block whose whole purpose is to replace a
    guess with a number.
    """
    looked_up: list[str] = []

    class _Watching:
        def facts_for(self, name: str) -> PackageFacts | None:
            looked_up.append(name)
            return PackageFacts(name=name, latest="0.0.7", summary="")

    text = describe_versions({"src"}, pinned=PINNED, registry=_Watching())

    assert looked_up == [], "the registry was asked about a package we do not depend on"
    assert "0.0.7" not in text
    assert "not declared" in text


def test_an_import_name_that_differs_from_its_distribution_is_resolved() -> None:
    """`import jwt` is PyJWT; `import yaml` is PyYAML.

    Read literally, both look undeclared, and the specialist is told a pinned
    dependency is unpinned.
    """
    pinned = {"pyjwt": "2.9.0", "pyyaml": "6.0.2"}
    registry = _Registry({"pyjwt": PackageFacts(name="PyJWT", latest="2.10.1", summary="")})

    text = describe_versions({"jwt", "yaml"}, pinned=pinned, registry=registry)

    assert "2.9.0" in text
    assert "6.0.2" in text
    assert "not declared" not in text
