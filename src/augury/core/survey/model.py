"""What a survey of a repository's deployment contains."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Service(BaseModel):
    """Something the repository builds and runs from its own source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    source_root: str = Field(
        default="",
        description="Repo-relative directory it is built from. Empty when the "
        "compose file gives an image rather than a build context.",
    )
    command: str = Field(
        default="",
        description="Kept verbatim: a worker's concurrency ceiling lives here "
        "and nowhere else in the repository.",
    )
    ports: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    environment: dict[str, str] = Field(default_factory=dict)

    @property
    def is_entrypoint(self) -> bool:
        """Whether traffic arrives here, as opposed to work being handed to it."""
        return bool(self.ports)


class BackingService(BaseModel):
    """Something the repository uses and did not write."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    image: str = ""
    kind: str = Field(
        default="unknown",
        description="What it is, so a specialist knows which failures apply to it",
    )


class Survey(BaseModel):
    """The deployment, as declared rather than as guessed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[Service, ...] = ()
    backing: tuple[BackingService, ...] = ()
    source_roots: tuple[str, ...] = Field(
        default=(),
        description="Directories that hold code this repository runs in "
        "production. The review is scoped to these when they are known.",
    )
    external: tuple[str, ...] = Field(
        default=(),
        description="Dependencies the compose file names but does not run, so "
        "nothing in the repository configures them",
    )
