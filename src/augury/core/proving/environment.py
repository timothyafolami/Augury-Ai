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

import re
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

# What an experiment's own process gets. Deliberately bare: a generated script
# should inherit nothing it was not handed.
BARE_PATH = "/usr/bin:/bin"


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
                # Not a bare `python`: Debian and Ubuntu ship `python3` with no
                # unversioned alias, which is most base images that are not
                # `python:*`. Probed against golang:1.22, which has
                # /usr/bin/python3 and nothing at /usr/bin/python. Guessing
                # wrong here fails as BROKEN with an exec error naming the
                # script, so the experiment looks defective and the image does
                # not. The fallback keeps an older image working.
                "sh",
                "-c",
                (
                    f"if command -v python3 >/dev/null 2>&1; then exec python3 {MOUNT_POINT}; "
                    f"else exec python {MOUNT_POINT}; fi"
                ),
            ]
        return [str(self.python), str(script)]

    def path(self, *, docker_at: Path | None = None) -> str:
        """The PATH the launching process needs.

        The bare path is for the experiment, and it is right: a generated
        script should inherit nothing. But `docker compose run` is the command
        that starts the container, and Docker Desktop installs to
        /usr/local/bin, which is not on it -- so a machine with docker running,
        already probed successfully, failed with "No such file or directory".
        """
        if self.kind != "compose" or docker_at is None:
            return BARE_PATH
        holding = str(docker_at.parent)
        if holding in BARE_PATH.split(":"):
            return BARE_PATH
        return f"{holding}:{BARE_PATH}"

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

    service, refused = _service_for(scope, survey)
    if service and available:
        return Environment(kind="compose", root=root, service=service)

    python = interpreter_for(root / scope[0] if scope else root)
    if refused:
        why = (
            f"the service built from the reviewed directory is named {refused!r}, which "
            "docker would read as one of its own flags rather than as a service, so the "
            "experiment ran on this machine instead"
        )
    elif service and not available:
        why = (
            f"docker is not running, so the {service} image could not be used and "
            "the experiment ran on this machine, where the repository's "
            "dependencies may not be installed"
        )
    else:
        why = "no service in the compose file builds from the reviewed directory"
    return Environment(kind="local", root=root, python=python, why=why)


# What compose itself permits, minus a leading dash. Docker reads `--dry-run`
# or `-d` in the service position as its own flag, which turns an experiment
# into a no-op and lets a reviewed repository suppress the proofs about it.
_A_PLAIN_NAME = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]*$")


def _is_a_plain_name(name: str) -> bool:
    """Whether this service name is safe to hand to docker as a positional."""
    return bool(_A_PLAIN_NAME.match(name))


def _covers(source_root: str, wanted: set[str]) -> bool:
    """Whether this service is built from a directory containing the scope.

    Narrowing to a subdirectory is the normal way to run a review, and
    `--scope backend/src/services` is still the image built from `backend`.
    Comparing for equality reported that no service builds from the reviewed
    directory, for a repository where one plainly does.

    Compared segment by segment, so `backend-tools` is not inside `backend`
    however the two strings sort.

    A service built from the repository root -- `build: .`, which the surveyor
    normalises to an empty string -- contains everything, including a narrowed
    scope. Treating that empty string as falsy dropped the commonest compose
    layout there is.
    """
    stripped = source_root.strip("/")
    if not stripped:
        return True
    root = stripped.split("/")
    if not wanted:
        return True
    return any(part.split("/")[: len(root)] == root for part in wanted)


def _service_for(scope: tuple[str, ...], survey: Survey) -> tuple[str, str]:
    """The service built from the directory under review, and one it refused.

    Where several are -- an API and four workers all built from `backend` --
    the one taking traffic is preferred: it is the likeliest to have the
    dependencies a request path touches.
    """
    wanted = {part.strip("/") for part in scope}
    candidates = [service for service in survey.services if _covers(service.source_root, wanted)]
    if not candidates:
        return "", ""

    serving = [service for service in candidates if service.is_entrypoint]
    ordered = serving or candidates

    # A compose file in a repository under review is untrusted input, and its
    # service names go into an argv where docker reads a leading dash as its
    # own flag. Rejecting one hostile name must not cost the review a service
    # that is fine, so the search continues past it.
    usable = [service for service in ordered if _is_a_plain_name(service.name)]
    if usable:
        return usable[0].name, ""
    return "", ordered[0].name
