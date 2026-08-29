"""Where an experiment runs: this machine, or the image the service is built from.

A repository whose dependencies live in a Docker image cannot have its claims
measured locally. No interpreter beside it has `jwt` or `fastapi`, because those
are installed when the image is built.

The survey already knows which service is built from which directory, so it
knows which image would have them. Running the experiment there is the
difference between proving a forecast about this repository and reporting that
the forecast could not be checked.

No test here starts a container. The command is built and asserted; running it
is the caller's problem and Docker's.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from augury.core.proving.environment import (
    BARE_PATH,
    Environment,
    choose_environment,
    docker_is_up,
)
from augury.core.survey.model import Service, Survey


def _survey() -> Survey:
    return Survey(
        services=(
            Service(name="api", source_root="backend", ports=("8000:8000",)),
            Service(name="worker", source_root="backend", command="celery -A x worker"),
            Service(name="web", source_root="frontend", ports=("3000:3000",)),
        ),
        source_roots=("backend", "frontend"),
    )


def test_a_service_built_from_the_reviewed_directory_is_chosen(tmp_path: Path) -> None:
    environment = choose_environment(
        root=tmp_path, scope=("backend",), survey=_survey(), docker_available=True
    )

    assert environment.kind == "compose"
    assert environment.service == "api"


def test_the_service_that_takes_traffic_is_preferred_over_a_worker(
    tmp_path: Path,
) -> None:
    """Both build from `backend`. The one serving requests is the likelier host."""
    environment = choose_environment(
        root=tmp_path, scope=("backend",), survey=_survey(), docker_available=True
    )

    assert environment.service == "api"


def test_a_scope_with_no_service_falls_back_to_this_machine(tmp_path: Path) -> None:
    environment = choose_environment(
        root=tmp_path, scope=("docs",), survey=_survey(), docker_available=True
    )

    assert environment.kind == "local"


def test_without_docker_it_runs_here_and_says_so(tmp_path: Path) -> None:
    environment = choose_environment(
        root=tmp_path, scope=("backend",), survey=_survey(), docker_available=False
    )

    assert environment.kind == "local"
    assert "docker" in environment.why.lower()


def test_the_compose_command_does_not_start_the_whole_stack(tmp_path: Path) -> None:
    """`--no-deps`: measuring one module must not boot Postgres and Redis."""
    environment = Environment(kind="compose", service="api", root=tmp_path)

    command = environment.command(Path("/scripts/x.py"))

    assert "--no-deps" in command
    assert "--rm" in command, "a container left behind per finding is a leak"
    assert "api" in command


def test_the_script_is_mounted_read_only(tmp_path: Path) -> None:
    """The experiment must not be able to rewrite itself mid-run."""
    environment = Environment(kind="compose", service="api", root=tmp_path)

    command = " ".join(environment.command(Path("/scripts/x.py")))

    assert ":ro" in command


def test_a_local_environment_runs_the_interpreter_it_was_given(tmp_path: Path) -> None:
    environment = Environment(kind="local", python=Path("/usr/bin/python3"), root=tmp_path)

    command = environment.command(Path("/scripts/x.py"))

    assert command[0] == "/usr/bin/python3"
    assert command[1] == "/scripts/x.py"


def test_an_installed_docker_whose_daemon_is_down_is_not_available() -> None:
    """The binary on PATH says nothing about whether anything will run.

    Docker Desktop quit is the common case on a laptop, and `docker compose
    run` against a dead daemon fails with a connection error rather than a
    measurement -- so every finding would come back BROKEN for a reason that
    has nothing to do with the code under review.
    """
    assert not docker_is_up(probe=lambda: (1, "Cannot connect to the Docker daemon"))


def test_a_running_daemon_is_available() -> None:
    assert docker_is_up(probe=lambda: (0, "Server Version: 28.0.1"))


def test_a_missing_binary_is_not_available() -> None:
    def missing() -> tuple[int, str]:
        raise FileNotFoundError("docker")

    assert not docker_is_up(probe=missing)


def test_a_slow_daemon_is_treated_as_down_rather_than_hanging_the_review() -> None:
    """A probe that times out must answer, not raise: the review continues."""

    def hangs() -> tuple[int, str]:
        raise subprocess.TimeoutExpired(cmd="docker", timeout=5.0)

    assert not docker_is_up(probe=hangs)


def test_a_scope_inside_a_build_context_still_finds_its_service() -> None:
    """`--scope backend/src/services` is still the `api` image.

    Matching required the scope to equal the build context, so reviewing any
    subdirectory of a service fell back to this machine -- and reported that
    no service builds from the reviewed directory, for a repository where one
    plainly does. Narrowing the scope is the normal way to run this.
    """
    chosen = choose_environment(
        root=Path("/repo"),
        scope=("backend/src/services",),
        survey=_survey(),
        docker_available=True,
    )

    assert chosen.kind == "compose"
    assert chosen.service == "api"


def test_a_scope_outside_every_build_context_still_falls_back() -> None:
    """A directory no service is built from has no image to borrow."""
    chosen = choose_environment(
        root=Path("/repo"),
        scope=("docs",),
        survey=_survey(),
        docker_available=True,
    )

    assert chosen.kind == "local"


def test_a_sibling_with_a_shared_prefix_is_not_a_match() -> None:
    """`backend-tools` is not inside `backend`, however it sorts."""
    chosen = choose_environment(
        root=Path("/repo"),
        scope=("backend-tools",),
        survey=_survey(),
        docker_available=True,
    )

    assert chosen.kind == "local"


def test_a_compose_run_can_find_the_docker_binary() -> None:
    """The experiment runs in a deliberately bare environment: PATH is
    /usr/bin:/bin so a generated script inherits nothing it was not given.

    Docker Desktop installs to /usr/local/bin, which is not on it, so the
    launcher failed with "No such file or directory: 'docker'" on a machine
    where docker was running and had already been found once. The sandbox is
    for the script; the command that starts the container has to be runnable.
    """
    compose = Environment(kind="compose", root=Path("/repo"), service="api")

    assert "/usr/local/bin" in compose.path(docker_at=Path("/usr/local/bin/docker"))


def test_the_bare_path_is_kept_for_a_local_run() -> None:
    """Nothing is added for a script that runs here: it gets what it always got."""
    local = Environment(kind="local", root=Path("/repo"))

    assert local.path(docker_at=Path("/usr/local/bin/docker")) == BARE_PATH


def test_a_docker_on_the_bare_path_adds_nothing() -> None:
    compose = Environment(kind="compose", root=Path("/repo"), service="api")

    assert compose.path(docker_at=Path("/usr/bin/docker")) == BARE_PATH


def test_no_docker_found_leaves_the_path_alone() -> None:
    compose = Environment(kind="compose", root=Path("/repo"), service="api")

    assert compose.path(docker_at=None) == BARE_PATH
