"""A service command names where its code starts running.

`celery -A src.tasks.celery_app worker -Q default` says that
`src/tasks/celery_app.py` is an entrypoint. Nothing in that file looks like one
to a signal detector -- no route decorator, no server -- so without reading the
command, every Celery task in the repository is unreachable.

On a real repository that was 107 modules of business logic marked as code no
request reaches, because the only thing that knew otherwise was the compose
file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.survey import entrypoint_refs

CASES = [
    ("celery -A src.tasks.celery_app worker -Q default --concurrency=1", ["src/tasks/celery_app"]),
    ("celery -A app.celery beat --loglevel=info", ["app/celery"]),
    ("uvicorn app.main:app --host 0.0.0.0 --port 8000", ["app/main"]),
    ("gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.wsgi:application", ["app/wsgi"]),
    ("python -m app.worker", ["app/worker"]),
    ("python manage.py runserver", ["manage"]),
    ("python backend/main.py", ["backend/main"]),
    ("node server.js", ["server"]),
    ("npm run start", []),
    ("", []),
]


@pytest.mark.parametrize(("command", "expected"), CASES)
def test_a_command_names_the_module_it_starts(command: str, expected: list[str]) -> None:
    assert list(entrypoint_refs(command)) == expected


def test_a_flag_value_is_not_mistaken_for_the_module() -> None:
    """`gunicorn -w 4 ...`: the first bare token is the value of `-w`."""
    assert entrypoint_refs("gunicorn -w 4 app.wsgi:application") == ("app/wsgi",)


def test_a_command_names_its_module_relative_to_the_build_context() -> None:
    """The map is keyed on repo-relative paths; a command is not."""
    from augury.core.survey.model import Service

    service = Service(
        name="worker",
        source_root="backend",
        command="celery -A src.tasks.celery_app worker",
    )

    assert service.entrypoints == ("backend/src/tasks/celery_app",)


def test_the_worker_module_is_reachable_once_the_command_is_read(tmp_path: Path) -> None:
    """End to end: the survey supplies the entrypoint the detector cannot see."""
    from augury.core.cartography import Cartographer

    (tmp_path / "src" / "tasks").mkdir(parents=True)
    for package in ("src", "src/tasks"):
        (tmp_path / package / "__init__.py").write_text("")
    (tmp_path / "src" / "tasks" / "celery_app.py").write_text(
        "import celery\n\nfrom src.tasks import pipeline\n\napp = celery.Celery()\n"
    )
    (tmp_path / "src" / "tasks" / "pipeline.py").write_text(
        "import sqlalchemy\n\n\ndef run():\n    return sqlalchemy\n"
    )

    blind = Cartographer(tmp_path).map()
    assert all(m.depth is None for m in blind.modules), "nothing should look like an entrypoint"

    informed = Cartographer(tmp_path, entrypoints=("src/tasks/celery_app",)).map()
    depths = {m.path: m.depth for m in informed.modules}

    assert depths["src/tasks/celery_app.py"] == 0
    assert depths["src/tasks/pipeline.py"] == 1
