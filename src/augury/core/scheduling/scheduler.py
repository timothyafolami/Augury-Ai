"""Choose the next module worth reading, and know when to stop.

A repository does not fit in a context window. The naive answers are to read
everything, which is unaffordable, or to read the first N files, which is
arbitrary. This picks by expected yield per dollar, learns from what previous
reads found, and records what it chose to skip so coverage is never overstated.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from augury.core.cartography import ModuleNode, RepoMap, Signal

ENTRYPOINT_WEIGHT = 2.0
CHURN_WEIGHT = 0.1
NEIGHBOUR_WEIGHT = 0.5


class Budget(BaseModel):
    """Spend ceiling for one review."""

    usd: float = Field(default=5.0, gt=0)


class Coverage(BaseModel):
    """What was read, what was not, and why. Reported, never implied."""

    analysed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    reason: str = ""


class Scheduler:
    """Selects modules by expected yield per dollar until the budget runs out.

    Value rises with blast radius (fan-in), with how many concerns a module
    touches, with churn, and for entrypoints. Cost rises with size. Modules
    importing something already found defective are boosted in proportion to
    how much was found there, because defects travel along the import graph.
    """

    def __init__(self, repo: RepoMap, budget: Budget | None = None) -> None:
        self._repo = repo
        self._budget = budget or Budget()
        self._spent = 0.0
        self._seen: set[str] = set()
        self._suspect: dict[str, int] = {}
        self.coverage = Coverage()

    def next(self) -> ModuleNode | None:
        """The next module worth reading, or None when the review is over."""
        candidates = [
            m for m in self._repo.modules if m.path not in self._seen and self._is_worth_reading(m)
        ]
        if not candidates:
            self._close("nothing left worth reading")
            return None

        if self._spent >= self._budget.usd:
            self._close("budget exhausted", remaining=candidates)
            return None

        return max(candidates, key=lambda m: (self._value(m), m.path))

    def record(self, module: ModuleNode, *, findings: int, spent_usd: float) -> None:
        """Report the outcome of reading a module, which steers what comes next."""
        self._seen.add(module.path)
        self._spent += spent_usd
        self.coverage.analysed.append(module.path)
        if findings > 0:
            self._suspect[module.path] = findings

    # -- scoring -----------------------------------------------------------

    @staticmethod
    def _is_worth_reading(module: ModuleNode) -> bool:
        """No signal means no specialist has anything to say about it."""
        return bool(module.signals)

    def _value(self, module: ModuleNode) -> float:
        blast_radius = 1.0 + module.fan_in
        breadth = float(len(module.signals))
        recency = 1.0 + CHURN_WEIGHT * module.churn
        entrypoint = ENTRYPOINT_WEIGHT if Signal.ENTRYPOINT in module.signals else 1.0
        neighbour = 1.0 + NEIGHBOUR_WEIGHT * sum(
            self._suspect.get(dependency, 0) for dependency in module.imports
        )
        cost = math.sqrt(max(module.loc, 1))

        return blast_radius * breadth * recency * entrypoint * neighbour / cost

    def _close(self, reason: str, remaining: list[ModuleNode] | None = None) -> None:
        self.coverage.reason = reason
        self.coverage.skipped = sorted(m.path for m in remaining or [])
