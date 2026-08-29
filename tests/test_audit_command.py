"""Reviewing a repository that is not one of the seeded cases.

`review --case B01` reviews a fixture. The thing this project is for is
somebody's own service, and until there is a command that takes a path, the
tool is a benchmark rather than a reviewer.

The command reads the deployment first: which directories hold services, what
each one runs, and where its code starts. Everything it prints before spending
anything is deterministic and free.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from augury.cli.main import app

COMPOSE = """
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [redis]
  worker:
    build: ./backend
    command: celery -A src.tasks.app worker --concurrency=1
  web:
    build: ./frontend
    ports: ["3000:3000"]
  redis:
    image: redis:7-alpine
"""


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    (tmp_path / "backend" / "src" / "tasks").mkdir(parents=True)
    for package in ("backend/src", "backend/src/tasks"):
        (tmp_path / package / "__init__.py").write_text("")
    (tmp_path / "backend" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n"
    )
    (tmp_path / "backend" / "src" / "tasks" / "app.py").write_text(
        "import celery\n\napp = celery.Celery()\n"
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.tsx").write_text("export function App() { return <div/>; }\n")
    return tmp_path


def test_survey_reports_the_deployment_without_spending_anything(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["survey", "--path", str(_repo(tmp_path))])

    assert result.exit_code == 0, result.output
    assert "backend" in result.output
    assert "worker" in result.output
    assert "redis" in result.output
    assert "--concurrency=1" in result.output


def test_survey_needs_no_api_key(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Mapping and surveying are deterministic, so they must not need one."""
    for variable in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(variable, raising=False)

    result = CliRunner().invoke(app, ["survey", "--path", str(_repo(tmp_path))])

    assert result.exit_code == 0, result.output


def test_survey_says_which_modules_no_request_reaches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "backend" / "orphan.py").write_text("import sqlalchemy\n\n\ndef f():\n    return 1\n")

    result = CliRunner().invoke(app, ["survey", "--path", str(repo), "--scope", "backend"])

    assert "orphan.py" in result.output


def test_a_scope_matching_nothing_fails_rather_than_reporting_a_clean_repository(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app, ["survey", "--path", str(_repo(tmp_path)), "--scope", "backernd"]
    )

    assert result.exit_code != 0
    assert "matched no files" in result.output


def test_review_accepts_a_path_as_well_as_a_case(tmp_path: Path) -> None:
    """The tool is for somebody's own service, not only for its own fixtures."""
    import inspect

    from augury.cli.main import review

    parameters = inspect.signature(review).parameters
    assert "path" in parameters
    assert "scope" in parameters
    assert "budget" in parameters


def test_review_refuses_both_a_case_and_a_path(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["review", "--case", "B01", "--path", str(_repo(tmp_path))])

    assert result.exit_code != 0
    assert "not both" in result.output


def test_review_needs_one_of_them(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["review"])

    assert result.exit_code != 0
    assert "--case" in result.output or "--path" in result.output
