"""How much of the engineering framework a review actually exercised.

The eight specialists are the framework. A review that never asked one of them
about a concern the code plainly raises has a gap, however many findings it
published elsewhere, and the report as it stands cannot show that: it lists
what was found, which is the wrong end of the question.

The metric is a share, and the denominator is the whole argument. A layer's
coverage is the modules raising its concern that were read for it, over the
modules raising its concern at all. A concern appearing in forty modules and
asked about in ten is 25%. Sharing a single repository-wide denominator would
let a review buy a high number by reading the cheap layers, and dividing by the
modules chosen instead of the modules that qualify would report 100% for every
run by construction, since a run reads what it chose to read.

A layer whose concern appears nowhere gets no number at all. Zero over zero is
arithmetically 1.0 and would draw a full bar under a heading nobody looked at,
which is the one shape of this display that can actively mislead. `None` is the
same refusal `scoring` makes for a rate with nothing to divide.

Nothing here is measured by this module. Occurrences come from the
cartographer's signals, reads from the scheduler's coverage, finding counts
from the findings. The one inference is whether a module the scheduler read
counts as read *for a given layer*, and every row states which of the two
answers it used in `basis`, because the inferred one errs upward.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from augury.core.cartography import RepoMap
from augury.core.findings import Finding
from augury.core.layers import LAYERS
from augury.core.scheduling import Coverage


class Basis(StrEnum):
    """Where a row's reviewed count came from."""

    ROUTED = "routed"
    SIGNALLED = "signalled"


class LayerCoverage(BaseModel):
    """One specialist: what it could have been asked about, and what it was."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    layer: str = Field(description="The specialist's key, as `layers` declares it")
    title: str = Field(
        description="The heading to print. Derived from the key rather than "
        "held in a table here, so a row cannot outlive the specialist it names."
    )
    occurrences: tuple[str, ...] = Field(
        description="Modules whose signals raise this layer's concern. The "
        "denominator, and it counts modules the review never reached."
    )
    reviewed: tuple[str, ...] = Field(
        description="Occurrences a specialist for this layer read. Always a "
        "subset of `occurrences`, so a path the map does not hold cannot enter."
    )
    share: float | None = Field(
        description="`reviewed` over `occurrences`, or None when the concern "
        "appears nowhere. None is not zero: it means the question does not "
        "arise in this repository, and it must not render as a full bar."
    )
    findings: int = Field(ge=0, description="Findings this specialist published")
    basis: Basis = Field(
        description="Where `reviewed` came from. 'routed' is measured: the "
        "caller supplied which specialists were asked about which module. "
        "'signalled' is derived: a module the scheduler read counts as read "
        "for every layer its signals route to. That is an upper bound, because "
        "triage narrows those specialists further and this cannot see it."
    )

    @property
    def appears_in(self) -> int:
        return len(self.occurrences)

    @property
    def read(self) -> int:
        return len(self.reviewed)


class EngineeringCoverage(BaseModel):
    """Every specialist's row, and the totals they have to reconcile against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    layers: tuple[LayerCoverage, ...] = Field(
        description="One row per specialist, in declaration order. A layer "
        "with nothing to report is present and empty rather than absent, or "
        "the framework renders smaller than it is."
    )
    modules: int = Field(ge=0, description="Modules on the map, the ceiling on any row")
    unattributed_findings: int = Field(
        ge=0,
        description="Findings naming no specialist. The layer on a finding is "
        "what the model wrote and `drafts` substitutes 'unknown' when it wrote "
        "nothing, so the rows can sum to less than the report's own total. "
        "Counted rather than dropped, because that difference is the reader's.",
    )


def engineering_coverage(
    repo: RepoMap,
    coverage: Coverage,
    findings: Sequence[Finding],
    *,
    routed: Mapping[str, Collection[str]] | None = None,
) -> EngineeringCoverage:
    """Measure one review against the framework it claims to apply.

    `routed` maps a module path to the specialists actually asked about it,
    which the trajectory records as triage decides them. Supply it and the
    reviewed count is a count; omit it and it is an upper bound, which each row
    declares. A path absent from a supplied `routed` counts as read for
    nothing, so a partial record understates rather than overstates.
    """
    was_read = set(coverage.analysed)
    published = Counter(finding.layer.strip().lower() for finding in findings)
    basis = Basis.SIGNALLED if routed is None else Basis.ROUTED

    rows: list[LayerCoverage] = []
    for layer in LAYERS:
        # Sorted rather than left in map order, so two runs of the same review
        # produce the same row and stay comparable, which is the reason
        # `specialists_for` returns declaration order.
        occurrences = tuple(sorted(m.path for m in repo.modules if m.signals & layer.signals))
        asked = [p for p in occurrences if p in was_read and _asked(layer.name, p, routed)]
        rows.append(
            LayerCoverage(
                layer=layer.name,
                title=layer.name.capitalize(),
                occurrences=occurrences,
                reviewed=tuple(asked),
                share=_share(len(asked), len(occurrences)),
                findings=published[layer.name],
                basis=basis,
            )
        )

    known = {layer.name for layer in LAYERS}
    return EngineeringCoverage(
        layers=tuple(rows),
        modules=len(repo.modules),
        unattributed_findings=sum(n for name, n in published.items() if name not in known),
    )


def _asked(layer: str, path: str, routed: Mapping[str, Collection[str]] | None) -> bool:
    """Whether a specialist for this layer read this module."""
    if routed is None:
        return True
    return layer in {name.strip().lower() for name in routed.get(path, ())}


def _share(reviewed: int, occurrences: int) -> float | None:
    """None when there is nothing to divide, so an absent concern reads as absent."""
    return reviewed / occurrences if occurrences else None
