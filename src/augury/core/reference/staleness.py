"""How far a repository's dependencies are from what the ecosystem ships.

Every rule here is arithmetic on two version strings and an answer from the
registry, so none of it costs a model call and none of it can be hallucinated.
That is the point: a model asked which version of a library is current will
answer from its training cutoff, confidently.
"""

from __future__ import annotations

import re
from typing import Protocol

from augury.core.reference.registry import PackageFacts
from augury.core.schema.model import SchemaFinding

# `1.2.3`, `2.0`, `10`. Anything else -- a git ref, a range, a local build --
# is not a comparison worth guessing at.
_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class _Registry(Protocol):
    def facts_for(self, name: str) -> PackageFacts | None: ...


def dependency_findings(pinned: dict[str, str], registry: _Registry) -> tuple[SchemaFinding, ...]:
    """Findings about the dependency list, in a stable order."""
    found: list[SchemaFinding] = []
    for name, version in sorted(pinned.items()):
        facts = registry.facts_for(name)
        if facts is None:
            # Not on the registry: an internal package, not a stale one.
            continue
        found.extend(_check(name, version, facts))
    return tuple(found)


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
