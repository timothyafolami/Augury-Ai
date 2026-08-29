"""How far a repository's dependencies are from what the ecosystem ships.

Every rule here is arithmetic on two version strings and an answer from the
registry, so none of it costs a model call and none of it can be hallucinated.
That is the point: a model asked which version of a library is current will
answer from its training cutoff, confidently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from augury.core.reference.registry import PackageFacts
from augury.core.schema.model import SchemaFinding

# `1.2.3`, `2.0`, `10`. Anything else -- a git ref, a range, a local build --
# is not a comparison worth guessing at.
_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class _Registry(Protocol):
    def facts_for(self, name: str) -> PackageFacts | None: ...


@dataclass(frozen=True)
class Audit:
    """What was checked, alongside what was found.

    Three consecutive runs against one repository printed 2, then 6, then 5
    findings, because a registry lookup that fails is silent -- correctly, since
    a review has to work offline. Silence is the right behaviour and the wrong
    report: a reader cannot tell "checked it, it is current" from "could not
    reach the registry", and those are opposite facts about the same package.
    """

    findings: tuple[SchemaFinding, ...]
    declared: int
    unreachable: tuple[str, ...]

    @property
    def checked(self) -> int:
        return self.declared - len(self.unreachable)

    @property
    def complete(self) -> bool:
        return not self.unreachable

    def coverage(self) -> str:
        """One line a reader can act on, or empty when there is nothing to say."""
        if self.complete:
            return ""
        missing = len(self.unreachable)
        names = ", ".join(self.unreachable[:4])
        more = f" and {missing - 4} more" if missing > 4 else ""
        return (
            f"{self.checked} of {self.declared} checked against the registry; "
            f"{missing} could not be reached ({names}{more}), so they are "
            "unknown rather than current"
        )


def dependency_findings(pinned: dict[str, str], registry: _Registry) -> tuple[SchemaFinding, ...]:
    """Findings about the dependency list, in a stable order."""
    return dependency_audit(pinned, registry).findings


def dependency_audit(pinned: dict[str, str], registry: _Registry) -> Audit:
    """Findings about the dependency list, and how much of it was checked."""
    found: list[SchemaFinding] = []
    unreachable: list[str] = []
    # Ask for all of them at once where the registry can: sequentially the
    # tail of a long requirements file times out behind its own queue.
    ahead = getattr(registry, "facts_for_many", None)
    if ahead is not None:
        ahead(tuple(pinned))
    for name, version in sorted(pinned.items()):
        facts = registry.facts_for(name)
        if facts is None:
            if not version:
                # An unpinned dependency is a fact about the declaration, not
                # about any published version, so it does not need a registry
                # to be true. Requiring one made the most basic finding here
                # depend on the most fragile resource.
                found.append(_unpinned_without_facts(name))
                continue
            # Either an internal package or a registry that did not answer.
            # From here the two are indistinguishable, which is the reason
            # this is reported as coverage rather than resolved as a finding.
            unreachable.append(name)
            continue
        found.extend(_check(name, version, facts))
    return Audit(findings=tuple(found), declared=len(pinned), unreachable=tuple(unreachable))


def _unpinned_without_facts(name: str) -> SchemaFinding:
    return SchemaFinding(
        rule="dependency-unpinned",
        path="requirements",
        line=1,
        detail=(
            f"`{name}` is declared with no version, so it installs whatever exists "
            "the day the image is built. That makes two deploys of one commit two "
            "different services"
        ),
        remediation=(f"Pin it to the version you have installed: pip freeze | grep -i {name}"),
    )


def _check(name: str, version: str, facts: PackageFacts) -> list[SchemaFinding]:
    if not version:
        return [
            SchemaFinding(
                rule="dependency-unpinned",
                path="requirements",
                line=1,
                detail=(
                    f"`{name}` is declared with no version, so it installs whatever "
                    f"exists the day the image is built -- currently {facts.latest}. "
                    "That makes two deploys of one commit two different services"
                ),
                remediation=f"Pin it: {name}=={facts.latest}",
            )
        ]

    behind = _majors_between(version, facts.latest)
    if behind < 1:
        return []

    plural = "major version" if behind == 1 else f"{behind} major versions"
    return [
        SchemaFinding(
            rule="dependency-major-versions-behind",
            path="requirements",
            line=1,
            detail=(
                f"`{name}` is pinned at {version} and the registry ships "
                f"{facts.latest}, released {facts.released or 'recently'}: "
                f"{plural} behind. A major version is where the defaults this "
                "code relies on are allowed to change"
            ),
            remediation=(
                f"Read {name}'s changelog between {version} and {facts.latest} "
                "before upgrading; the gap is where its breaking changes live"
            ),
        )
    ]


def _majors_between(pinned: str, latest: str) -> int:
    """Major versions between two releases, or 0 if that cannot be said.

    Only the major number counts, including below 1.0. Semver permits a 0.x
    minor to break, but libraries that live at 0.x ship minors constantly --
    FastAPI moved 0.136 to 0.141 in a few months -- and reporting each as a
    breaking gap would bury the one dependency that really is a major behind
    under a dozen that are merely current-ish.
    """
    left, right = _VERSION.match(pinned), _VERSION.match(latest)
    if left is None or right is None:
        return 0
    return max(0, int(right.group(1)) - int(left.group(1)))
