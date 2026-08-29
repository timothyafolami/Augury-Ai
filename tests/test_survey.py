"""Reading the deployment before reading the code.

A repository is not a flat list of files ranked by fan-in. It is a set of
services, each built from a directory, each running a command, each depending
on things it did not write. That structure is declared in the compose file, and
reading it first is what tells you which directory is the backend, what the
backend is written in, how many workers it runs, and what it talks to.

Reviewing without it means ranking a frontend component and a Celery worker on
the same scale, and spending a budget on code that never serves a request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.survey import Surveyor

COMPOSE = """
services:
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${PORT:-10000}:${PORT:-10000}"
    environment:
      REDIS_URL: redis://redis:6379/0
      QDRANT_URL: http://qdrant:6333
    depends_on:
      redis:
        condition: service_healthy
      qdrant:
        condition: service_started

  worker_default:
    build:
      context: ./backend
    command: celery -A src.tasks.celery_app worker -Q default --concurrency=1
    depends_on: { redis: { condition: service_healthy } }

  web:
    build: ./frontend
    ports: ["3000:3000"]

  redis:
    image: redis:7-alpine

  qdrant:
    image: qdrant/qdrant:v1.9.0
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    for directory in ("backend/src/tasks", "frontend/src", "docs"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "backend" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n"
    )
    (tmp_path / "backend" / "src" / "tasks" / "celery_app.py").write_text("import celery\n")
    (tmp_path / "frontend" / "src" / "App.tsx").write_text(
        "export function App() { return <div/>; }\n"
    )
    return tmp_path


def test_the_services_that_run_our_code_are_separated_from_the_ones_we_only_use(
    repo: Path,
) -> None:
    survey = Surveyor(repo).survey()

    assert {s.name for s in survey.services} == {"api", "worker_default", "web"}
    assert {b.name for b in survey.backing} == {"redis", "qdrant"}


def test_a_backing_service_is_classified_by_what_it_is(repo: Path) -> None:
    kinds = {b.name: b.kind for b in survey_of(repo).backing}

    assert kinds == {"redis": "cache or queue", "qdrant": "vector store"}


def survey_of(repo: Path):  # type: ignore[no-untyped-def]
    return Surveyor(repo).survey()


def test_each_service_names_the_directory_it_is_built_from(repo: Path) -> None:
    roots = {s.name: s.source_root for s in survey_of(repo).services}

    assert roots == {"api": "backend", "worker_default": "backend", "web": "frontend"}


def test_the_command_a_service_runs_is_kept_because_it_carries_the_concurrency(
    repo: Path,
) -> None:
    """`--concurrency=1` is a capacity ceiling, and it is only in the command."""
    worker = next(s for s in survey_of(repo).services if s.name == "worker_default")

    assert "--concurrency=1" in worker.command


def test_a_service_declares_what_it_depends_on(repo: Path) -> None:
    api = next(s for s in survey_of(repo).services if s.name == "api")

    assert set(api.depends_on) == {"redis", "qdrant"}


def test_a_repository_with_no_compose_file_still_surveys(tmp_path: Path) -> None:
    """Most repositories have no compose file, and must not be unreviewable."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("from fastapi import FastAPI\n")

    survey = Surveyor(tmp_path).survey()

    assert survey.services == ()
    assert survey.source_roots == ()


# -- scoping ---------------------------------------------------------------


def test_the_map_can_be_scoped_to_one_source_root(repo: Path) -> None:
    """ "We have no business with the frontend" has to be expressible.

    Mapping every directory means ranking a React component and a Celery worker
    on one scale, and spending a budget on code that never serves a request.
    """
    from augury.core.cartography import Cartographer

    everything = Cartographer(repo).map()
    backend_only = Cartographer(repo, scope=("backend",)).map()

    assert any(m.path.startswith("frontend/") for m in everything.modules)
    assert {m.path for m in backend_only.modules} == {
        "backend/main.py",
        "backend/src/tasks/celery_app.py",
    }


def test_a_scope_that_matches_nothing_is_an_error_not_an_empty_review(repo: Path) -> None:
    """Reviewing nothing and reporting no findings looks like a clean bill."""
    from augury.core.cartography import Cartographer

    with pytest.raises(ValueError, match="no files"):
        Cartographer(repo, scope=("backernd",)).map()
