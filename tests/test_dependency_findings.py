"""What the dependency list says, without asking a model to remember it.

A major version behind is a fact about two strings and a registry. It costs no
model call, it cannot be hallucinated, and on a real repository it is the
difference between "we use pandas" and "we use pandas 2 while the ecosystem
ships 3".

Unpinned is the other half. `celery` with no version installs whatever exists
the day the image is built, so two deploys of one commit are two different
services -- which is the defect underneath most "works on my machine".
"""

from __future__ import annotations

from augury.core.reference import PackageFacts
from augury.core.reference.staleness import dependency_findings


class _Registry:
    def __init__(self, facts: dict[str, PackageFacts]) -> None:
        self._facts = facts

    def facts_for(self, name: str) -> PackageFacts | None:
        return self._facts.get(name)


def _facts(name: str, latest: str) -> PackageFacts:
    return PackageFacts(name=name, latest=latest, summary="", released="2026-07-22")


def test_a_major_version_behind_is_reported() -> None:
    findings = dependency_findings(
        {"pandas": "2.3.0"}, _Registry({"pandas": _facts("pandas", "3.0.5")})
    )

    assert [f.rule for f in findings] == ["dependency-major-versions-behind"]
    assert "2.3.0" in findings[0].detail
    assert "3.0.5" in findings[0].detail


def test_two_majors_behind_says_two() -> None:
    findings = dependency_findings(
        {"cachetools": "5.5.0"}, _Registry({"cachetools": _facts("cachetools", "7.1.7")})
    )

    assert "2 major versions" in findings[0].detail


def test_a_minor_version_behind_is_not_reported() -> None:
    """Being current is not the bar. Being a major behind is."""
    findings = dependency_findings(
        {"fastapi": "0.136.0"}, _Registry({"fastapi": _facts("fastapi", "0.141.1")})
    )

    assert findings == ()


def test_an_unpinned_dependency_is_reported() -> None:
    findings = dependency_findings({"celery": ""}, _Registry({"celery": _facts("celery", "5.6.3")}))

    assert [f.rule for f in findings] == ["dependency-unpinned"]
    assert "two deploys of one commit" in findings[0].detail


def test_a_package_the_registry_does_not_know_is_left_alone() -> None:
    """An internal package is not a stale one."""
    assert dependency_findings({"our-internal-lib": "1.0.0"}, _Registry({})) == ()


def test_a_version_that_does_not_parse_is_left_alone() -> None:
    """`>=2.0,<3` and git URLs are not comparisons this should guess at."""
    findings = dependency_findings(
        {"weird": "main"}, _Registry({"weird": _facts("weird", "3.0.0")})
    )

    assert findings == ()


def test_a_zero_major_package_is_judged_on_its_major_like_everything_else() -> None:
    """Semver lets a 0.x minor break, and reporting each one buries the real gaps.

    Libraries that live at 0.x ship minors constantly. Counting those as
    breaking would put a dozen merely-current-ish dependencies alongside the
    one that is genuinely a major behind, which is how a findings list stops
    being read.
    """
    findings = dependency_findings(
        {"httpx": "0.27.0"}, _Registry({"httpx": _facts("httpx", "0.28.1")})
    )

    assert findings == ()
