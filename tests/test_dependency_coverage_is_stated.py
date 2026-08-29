"""A dependency count that depends on network luck must say so.

Three consecutive survey runs against one repository printed 2, then 6, then
5 findings. Nothing about the repository changed; PyPI lookups fail
intermittently and every failure here is silent by design, because a review
has to work offline.

Silence is the right behaviour and the wrong report. A reader cannot tell
"checked it, it is current" from "could not reach the registry", and those
are opposite facts.
"""

from __future__ import annotations

from augury.core.reference.registry import PackageFacts
from augury.core.reference.staleness import dependency_audit


class _Registry:
    def __init__(self, known: dict[str, PackageFacts]) -> None:
        self._known = known

    def facts_for(self, name: str) -> PackageFacts | None:
        return self._known.get(name)


_CURRENT = PackageFacts(name="redis", latest="7.0.0", released="2026-01-01", summary="")


def test_a_package_the_registry_could_not_answer_for_is_counted() -> None:
    audit = dependency_audit({"redis": "4.0.0", "offline": "1.0"}, _Registry({"redis": _CURRENT}))
    assert audit.unreachable == ("offline",)


def test_the_number_checked_excludes_the_ones_that_failed() -> None:
    audit = dependency_audit({"redis": "4.0.0", "offline": "1.0"}, _Registry({"redis": _CURRENT}))
    assert audit.checked == 1
    assert audit.declared == 2


def test_findings_are_unchanged_by_the_accounting() -> None:
    audit = dependency_audit({"redis": "4.0.0", "offline": "1.0"}, _Registry({"redis": _CURRENT}))
    assert [f.rule for f in audit.findings] == ["dependency-major-versions-behind"]


def test_an_unpinned_package_needs_no_registry_and_is_not_unreachable() -> None:
    """It is a finding about the declaration, not about any published version."""
    audit = dependency_audit({"supabase": ""}, _Registry({}))
    assert audit.unreachable == ()
    assert [f.rule for f in audit.findings] == ["dependency-unpinned"]


def test_everything_answered_reads_as_complete() -> None:
    audit = dependency_audit({"redis": "7.0.0"}, _Registry({"redis": _CURRENT}))
    assert audit.complete


def test_one_unanswered_package_makes_the_audit_incomplete() -> None:
    audit = dependency_audit({"redis": "4.0.0", "offline": "1.0"}, _Registry({"redis": _CURRENT}))
    assert not audit.complete
