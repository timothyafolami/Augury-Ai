"""Where an experiment runs: this machine, or the image the service is built from.

A repository whose dependencies live in a Docker image cannot have its claims
measured locally. No interpreter beside it has `jwt` or `fastapi`, because those
are installed when the image is built -- which is why the first real proving run
returned "printed no number" for every finding.

The survey already knows which service is built from which directory, so it
knows which image would have them. Running the experiment there is the
difference between proving a forecast about a repository and reporting that the
forecast could not be checked.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from augury.core.proving.interpreter import interpreter_for
from augury.core.survey.model import Survey

# Where the script is mounted inside the container. Outside the working
# directory so it cannot collide with the repository's own files.
MOUNT_POINT = "/tmp/augury-experiment.py"


@dataclass(frozen=True)
class Environment:
    """How to execute one experiment."""

    kind: str  # "local" or "compose"
    root: Path
    service: str = ""
    python: Path = field(default_factory=lambda: Path(sys.executable))
    why: str = ""

    def command(self, script: Path) -> list[str]:
        """The argv that runs this script."""
        if self.kind == "compose":
            return [
                "docker",
                "compose",
                "run",
                # A container per finding that is never removed is a leak, and
                # booting Postgres and Redis to measure one module is a review
                # that nobody runs twice.
                "--rm",
                "--no-deps",
                "--volume",
                f"{script}:{MOUNT_POINT}:ro",
                self.service,
                "python",
                MOUNT_POINT,
            ]
        return [str(self.python), str(script)]

    @property
    def describes(self) -> str:
        if self.kind == "compose":
            return f"the {self.service} image"
        return str(self.python)


def choose_environment(
    *,
    root: Path,
    scope: tuple[str, ...],
    survey: Survey,
    docker_available: bool | None = None,
) -> Environment:
    """Where this repository's code can actually be imported.

    Falls back to this machine rather than refusing: a script with no
    third-party imports still runs, and refusing would turn a measurable claim
    into an unmeasurable one for tidiness.
    """
    available = shutil.which("docker") is not None if docker_available is None else docker_available

    service = _service_for(scope, survey)
    if service and available:
        return Environment(kind="compose", root=root, service=service)

    python = interpreter_for(root / scope[0] if scope else root)
    if service and not available:
        why = (
            f"docker is not available, so the {service} image could not be used and "
            "the experiment ran on this machine, where the repository's "
            "dependencies may not be installed"
        )
    else:
        why = "no service in the compose file builds from the reviewed directory"
    return Environment(kind="local", root=root, python=python, why=why)


def _service_for(scope: tuple[str, ...], survey: Survey) -> str:
    """The service built from the directory under review.

    Where several are -- an API and four workers all built from `backend` --
    the one taking traffic is preferred: it is the likeliest to have the
    dependencies a request path touches.
    """
    wanted = {part.strip("/") for part in scope} or {""}
    candidates = [
        service
        for service in survey.services
        if not wanted or service.source_root in wanted or (not scope and service.source_root)
    ]
    if not candidates:
        return ""
    serving = [service for service in candidates if service.is_entrypoint]
    return (serving or candidates)[0].name
