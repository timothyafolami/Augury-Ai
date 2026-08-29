"""What the free command prints is the first thing anyone sees.

Two defects this pins, both found by reading real output rather than by
running the tests: a command truncated at 70 characters cut off
`--concurrency=1`, which is the single finding the survey exists to surface;
and the language mix printed as a raw Python dict.
"""

from __future__ import annotations

from rich.console import Console

from augury.cli.rendering import (
    capacity_flags,
    languages_read,
    runs_summary,
    service_table,
)
from augury.core.survey.model import Service


def test_a_concurrency_ceiling_survives_the_command_column() -> None:
    """The flag the survey exists to surface must not be the part cut off."""
    command = (
        "celery -A src.tasks.celery_app worker -Q alignment --loglevel=info "
        "--concurrency=1 --hostname=alignment@%h"
    )
    assert "--concurrency=1" in capacity_flags(command)


def test_a_command_with_no_ceiling_says_so_rather_than_inventing_one() -> None:
    assert capacity_flags("celery -A src.tasks.celery_app beat --loglevel=info") == ""


def test_pool_and_prefetch_are_ceilings_too() -> None:
    flags = capacity_flags("celery -A x worker --pool=solo --prefetch-multiplier=1")
    assert "--pool=solo" in flags
    assert "--prefetch-multiplier=1" in flags


def test_uvicorn_workers_is_a_ceiling() -> None:
    assert "--workers 4" in capacity_flags("uvicorn app.main:app --workers 4 --port 80")


def test_the_language_mix_reads_as_prose_not_as_a_dict() -> None:
    said = languages_read({"python": 224, "typescript": 12})
    assert "{" not in said
    assert said == "224 python, 12 typescript"


def test_the_largest_language_comes_first() -> None:
    assert languages_read({"go": 3, "python": 90}).startswith("90 python")


def test_no_modules_says_nothing_rather_than_an_empty_brace() -> None:
    assert languages_read({}) == ""


def test_a_celery_worker_reads_as_its_queue_not_as_its_first_forty_characters() -> None:
    """Six workers whose commands share a prefix are told apart by the queue."""
    said = runs_summary(
        "celery -A src.tasks.celery_app worker -Q alignment --loglevel=info "
        "--concurrency=1 --hostname=alignment@%h"
    )
    assert said == "celery worker -Q alignment"


def test_a_beat_scheduler_is_not_confused_with_a_worker() -> None:
    assert runs_summary("celery -A src.tasks.celery_app beat --loglevel=info") == "celery beat"


def test_a_web_server_reads_as_the_app_it_serves() -> None:
    assert runs_summary("uvicorn app.main:app --host 0.0.0.0 --workers 4") == "uvicorn app.main:app"


def test_an_empty_command_stays_empty_rather_than_becoming_a_guess() -> None:
    assert runs_summary("") == ""


def test_an_unrecognised_command_keeps_its_own_first_words() -> None:
    """Better a short true thing than a summary of a shape we do not know."""
    assert runs_summary("./bin/serve --port 80") == "./bin/serve"


def _rendered(width: int = 80) -> str:
    """What a reader at this terminal width actually sees."""
    console = Console(width=width, force_terminal=False)
    with console.capture() as caught:
        console.print(service_table(_SERVICES))
    return caught.get()


_SERVICES = (
    Service(
        name="worker_alignment",
        source_root="backend",
        command=(
            "celery -A src.tasks.celery_app worker -Q alignment --loglevel=info "
            "--concurrency=1 --hostname=alignment@%h"
        ),
    ),
    Service(name="api", source_root="backend", ports=("${PORT:-10000}:${PORT:-10000}",)),
)


def test_the_capacity_ceiling_is_legible_on_an_eighty_column_terminal() -> None:
    """The demo is recorded in a terminal, not in a wide editor.

    An ellipsis here loses the one fact the survey exists to surface, so this
    asserts the rendered characters rather than the string handed to Rich.
    """
    assert "--concurrency=1" in _rendered(width=80)


def test_the_queue_that_tells_six_workers_apart_survives_too() -> None:
    assert "alignment" in _rendered(width=80)


def test_a_service_with_no_command_still_says_it_takes_traffic() -> None:
    """`-` in every column would hide the one service requests arrive at."""
    assert "serves" in runs_summary("", ports=("${PORT:-10000}:${PORT:-10000}",))


def test_a_command_wins_over_the_port_it_listens_on() -> None:
    said = runs_summary("uvicorn app.main:app --workers 4", ports=("8000:8000",))
    assert said == "uvicorn app.main:app"


def test_a_port_written_as_a_shell_default_reads_as_the_number() -> None:
    """`${PORT:-10000}:${PORT:-10000}` is one port, not the string `-10000}`.

    Compose files written for a platform that injects PORT use this form, and
    splitting on `:` finds the `:-` of the default rather than the mapping.
    """
    assert runs_summary("", ports=("${PORT:-10000}:${PORT:-10000}",)) == "serves :10000"


def test_a_plain_mapping_still_reads_as_the_container_port() -> None:
    assert runs_summary("", ports=("8081:8080",)) == "serves :8080"


def test_a_port_with_no_number_at_all_says_nothing() -> None:
    assert runs_summary("", ports=("${PORT}",)) == ""
