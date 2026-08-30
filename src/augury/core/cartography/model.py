"""What the map is made of.

A `Signal` is evidence that a module touches a concern one of the lab layers
owns. Signals are what Triage routes on, so they must be earned from the
source rather than guessed: an empty module carries no signals and therefore
costs nothing to review.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Signal(StrEnum):
    """Concerns detectable from source, each owned by one lab layer."""

    CONCURRENCY = "concurrency"  # 01-machine: threads, tasks, shared state
    NETWORK = "network"  # 02-network: clients, pools, timeouts
    DATA = "data"  # 03-data: ORM sessions, queries, transactions
    DISTRIBUTED = "distributed"  # 04-distributed: queues, retries, idempotency
    FAILURE = "failure"  # 05-failure: backoff, shedding, circuit breaking
    OBSERVABILITY = "observability"  # 06-observability: logging, metrics, tracing
    SECURITY = "security"  # 07-security: secrets, auth, raw SQL
    CRAFT = "craft"  # 08-craft: error contracts, module depth, coupling
    ENTRYPOINT = "entrypoint"  # where load enters the system


class ModuleNode(BaseModel):
    """One source file, and everything the map knows about it."""

    path: str = Field(description="Repo-relative POSIX path")
    loc: int = Field(ge=0, description="Non-blank source lines")
    imports: frozenset[str] = Field(
        default_factory=frozenset, description="Repo-relative paths this module imports"
    )
    signals: frozenset[Signal] = Field(default_factory=frozenset)
    unmatched_imports: frozenset[str] = Field(
        default_factory=frozenset,
        description="External imports no detector recognised. 'No signal' is a "
        "claim about the code; this distinguishes it from a gap in our table.",
    )
    external: frozenset[str] = Field(
        default_factory=frozenset,
        description="Third-party packages this module imports. What a "
        "specialist needs to be told the installed version of, rather than "
        "recall one.",
    )
    fan_in: int = Field(default=0, ge=0, description="How many modules import this one")
    depth: int | None = Field(
        default=None,
        ge=0,
        description="Hops along the import graph from the nearest entrypoint. "
        "0 is where a request arrives. None means nothing a request reaches "
        "imports this, which is a claim about the module rather than a gap.",
    )
    churn: int = Field(default=0, ge=0, description="Commits touching this file")


class Exclusion(BaseModel):
    """One category of file the walk never mapped, and why.

    A reason and a count, never the paths. A monorepo excludes tens of
    thousands of vendored files, and a reviewer that answers "what did you not
    look at?" with forty thousand lines has answered nothing.
    """

    reason: str = Field(description="Why nothing in this category was read")
    count: int = Field(ge=0, description="How many files were excluded for that reason")


class RepoMap(BaseModel):
    """The whole repository, as the Scheduler sees it."""

    root: str
    modules: list[ModuleNode] = Field(default_factory=list)
    unparsed: list[str] = Field(
        default_factory=list, description="Files that failed to parse, recorded not hidden"
    )
    skipped: dict[str, str] = Field(
        default_factory=dict,
        description="Files deliberately not read, mapped to why. Never silent.",
    )
    unreachable: tuple[str, ...] = Field(
        default=(),
        description="Modules no entrypoint reaches. Empty when the repository "
        "declares no entrypoint at all, because then nothing is reachable and "
        "calling everything unreachable would say nothing.",
    )
    context: dict[str, str] = Field(
        default_factory=dict,
        description="Deployment configuration that sets the conditions a module "
        "runs under. Sent alongside every module, because a defect is often the "
        "relationship between a number here and a number in the source.",
    )
    excluded: dict[str, Exclusion] = Field(
        default_factory=dict,
        description="Files that never entered the map, by category. `skipped` "
        "names files that were considered and set aside; this counts the ones "
        "the walk never offered, which in a large repository is most of it. "
        "Empty when nothing was excluded, rather than a row of zeroes.",
    )

    def module(self, path: str) -> ModuleNode:
        for module in self.modules:
            if module.path == path:
                return module
        raise KeyError(f"{path} is not in the map")
