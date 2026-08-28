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
    fan_in: int = Field(default=0, ge=0, description="How many modules import this one")
    churn: int = Field(default=0, ge=0, description="Commits touching this file")


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

    def module(self, path: str) -> ModuleNode:
        for module in self.modules:
            if module.path == path:
                return module
        raise KeyError(f"{path} is not in the map")
