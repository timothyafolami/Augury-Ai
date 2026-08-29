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

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from augury.core.proving.interpreter import interpreter_for
from augury.core.survey.model import Survey

# Long enough for a laptop daemon that is awake but busy; short enough that a
# daemon which is starting up does not hold the review.
PROBE_TIMEOUT = 5.0

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


def docker_is_up(*, probe: Callable[[], tuple[int, str]] | None = None) -> bool:
    """Whether a container would actually start.

    A `docker` binary on PATH is not the question -- Docker Desktop being quit
    is the common case on a laptop, and a compose run against a dead daemon
    fails with a connection error rather than a measurement, which would mark
    every finding BROKEN for a reason unrelated to the code under review.
    """
    ask = probe or _ask_the_daemon
    try:
        code, _ = ask()
    except (OSError, subprocess.SubprocessError):
        # No binary, or a daemon too slow to answer. Both mean: not here.
        return False
    return code == 0


def _ask_the_daemon() -> tuple[int, str]:
    """The cheapest question that requires the daemon to answer it."""
    done = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT,
    )
    return done.returncode, (done.stdout + done.stderr).strip()


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
    available = docker_is_up() if docker_available is None else docker_available

    service = _service_for(scope, survey)
    if service and available:
        return Environment(kind="compose", root=root, service=service)

    python = interpreter_for(root / scope[0] if scope else root)
    if service and not available:
        why = (
            f"docker is not running, so the {service} image could not be used and "
            "the experiment ran on this machine, where the repository's "
            "dependencies may not be installed"
        )
    else:
        why = "no service in the compose file builds from the reviewed directory"
    return Environment(kind="local", root=root, python=python, why=why)


def _covers(source_root: str, wanted: set[str]) -> bool:
    """Whether this service is built from a directory containing the scope.

    Narrowing to a subdirectory is the normal way to run a review, and
    `--scope backend/src/services` is still the image built from `backend`.
    Comparing for equality reported that no service builds from the reviewed
    directory, for a repository where one plainly does.

    Compared segment by segment, so `backend-tools` is not inside `backend`
    however the two strings sort.
    """
    root = source_root.strip("/").split("/")
    return any(part.split("/")[: len(root)] == root for part in wanted)


def _service_for(scope: tuple[str, ...], survey: Survey) -> str:
    """The service built from the directory under review.

    Where several are -- an API and four workers all built from `backend` --
    the one taking traffic is preferred: it is the likeliest to have the
    dependencies a request path touches.
    """
    wanted = {part.strip("/") for part in scope}
    candidates = [
        service
        for service in survey.services
        if service.source_root and (not wanted or _covers(service.source_root, wanted))
    ]
    if not candidates:
        return ""
    serving = [service for service in candidates if service.is_entrypoint]
    return (serving or candidates)[0].name
