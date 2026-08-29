"""Choose the next module worth reading, and know when to stop.

A repository does not fit in a context window. The naive answers are to read
everything, which is unaffordable, or to read the first N files, which is
arbitrary. This picks by expected yield per dollar, learns from what previous
reads found, and reports every file it did not read together with the reason,
because coverage overstated by silence is worse than no coverage number.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from augury.core.cartography import ModuleNode, RepoMap, Signal

ENTRYPOINT_WEIGHT = 2.0
CHURN_WEIGHT = 0.1
NEIGHBOUR_WEIGHT = 0.5
MICRO_USD = 1_000_000


class Budget(BaseModel):
    """Spend ceiling for one review, and what a read is expected to cost.

    The rate exists so the ceiling can be enforced *before* a module is issued.
    A limit checked only after the money is gone is not a limit.
    """

    usd: float = Field(default=5.0, gt=0)
    usd_per_1k_loc: float = Field(default=0.02, gt=0)
    calls_per_module: int = Field(
        default=1,
        ge=1,
        description="How many times an arm reads one module. A pipeline that "
        "triages and then asks several specialists reads it several times, and "
        "a ceiling that assumed one read would be no ceiling at all.",
    )


class Coverage(BaseModel):
    """What was read, what was not and why, and why the review ended."""

    analysed: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(
        default_factory=dict, description="Unread path to the reason it was not read"
    )
    stopped_because: str = Field(
        default="still running",
        description="Why the review ended. 'still running' means it has not.",
    )


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
        # Money is counted in integers. Ten one-cent reads sum to less than a
        # dime in binary floating point, which buys an eleventh read.
        self._spent_micros = 0
        self._budget_micros = round(self._budget.usd * MICRO_USD)
        self._seen: set[str] = set()
        self._suspect: dict[str, int] = {}
        self._stopped_because = "still running"
        self.coverage_analysed: list[str] = []

    @property
    def coverage(self) -> Coverage:
        """Computed on read, never written on one exit path.

        The first version wrote this only when `next()` was about to return
        None, so a caller that stopped for any other reason -- a wall-clock
        cap, a rate limit, an exception in the fan-out -- published an empty
        skip list that reads as full coverage. That is precisely when it was
        least true.
        """
        return Coverage(
            analysed=list(self.coverage_analysed),
            skipped={
                **{path: "unparsed" for path in self._repo.unparsed},
                **dict(self._repo.skipped),
                **{module.path: self._why_skipped(module) for module in self._unread()},
            },
            stopped_because=self._stopped_because,
        )

    @staticmethod
    def _why_skipped(module: ModuleNode) -> str:
        """Distinguish a fact about the code from a gap in our detectors."""
        if module.signals:
            return "budget"
        if module.unmatched_imports:
            return "no detector matched its imports"
        return "no signal"

    def next(self) -> ModuleNode | None:
        """The next module worth reading, or None when the review is over."""
        candidates = [m for m in self._unread() if self._is_worth_reading(m)]

        if not candidates:
            self._close("nothing left worth reading")
            return None

        affordable = [m for m in candidates if self._fits(m)]
        if not affordable:
            reason = (
                "budget exhausted"
                if self._spent_micros >= self._budget_micros
                else "nothing left fits the remaining budget"
            )
            self._close(reason)
            return None

        return max(affordable, key=lambda m: (self._value(m), m.path))

    def record(self, module: ModuleNode, *, findings: int, spent_usd: float) -> None:
        """Report the outcome of reading a module, which steers what comes next.

        Idempotent per module: a caller that records twice does not pay twice.
        """
        if module.path in self._seen:
            return
        self._seen.add(module.path)
        self._spent_micros += round(spent_usd * MICRO_USD)
        self.coverage_analysed.append(module.path)
        if findings > 0:
            self._suspect[module.path] = findings

    # -- selection ---------------------------------------------------------

    def _unread(self) -> list[ModuleNode]:
        return [m for m in self._repo.modules if m.path not in self._seen]

    @staticmethod
    def _is_worth_reading(module: ModuleNode) -> bool:
        """No signal means no specialist has anything to say about it."""
        return bool(module.signals)

    def _fits(self, module: ModuleNode) -> bool:
        return self._spent_micros + self._estimate_micros(module) <= self._budget_micros

    def _estimate_micros(self, module: ModuleNode) -> int:
        per_read = module.loc / 1000 * self._budget.usd_per_1k_loc
        return round(per_read * self._budget.calls_per_module * MICRO_USD)

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

    # -- reporting ---------------------------------------------------------

    def _close(self, reason: str) -> None:
        """Record why the review ended. What was skipped is derived on read."""
        self._stopped_because = reason
