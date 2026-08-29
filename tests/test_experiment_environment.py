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

from pathlib import Path

from augury.core.proving.environment import Environment, choose_environment
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
