"""A module is not the unit a defect lives in.

The first head-to-head found nothing where a single prompt found the defect,
because reading one module at a time throws away the relationship between
files. The seeded pool defect is `pool_size=5` in one file and `--workers 8` in
another; neither is wrong alone, and a reviewer shown only one of them is right
to decline.

So a specialist gets the module *and* the deployment configuration that sets
the concurrency it operates under.
"""

from pathlib import Path

from augury.core.cartography import Cartographer


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_collects_the_deployment_files_that_set_concurrency(tmp_path: Path) -> None:
    write(tmp_path, "Dockerfile", 'CMD ["uvicorn", "app.main:app", "--workers", "8"]\n')
    write(tmp_path, "app/db.py", "import sqlalchemy\n")

    context = Cartographer(tmp_path).map().context

    assert "Dockerfile" in context
    assert "--workers" in context["Dockerfile"]


def test_collects_compose_and_dependency_manifests(tmp_path: Path) -> None:
    write(tmp_path, "docker-compose.yml", "services:\n  api:\n    build: .\n")
    write(tmp_path, "requirements.txt", "fastapi==0.115.0\n")
    write(tmp_path, "app/db.py", "import sqlalchemy\n")

    context = Cartographer(tmp_path).map().context

    assert {"docker-compose.yml", "requirements.txt"} <= set(context)


def test_ordinary_source_is_not_ambient_context(tmp_path: Path) -> None:
    """Context is sent with every module, so anything in it is paid for many
    times over. It earns its place only if it changes how the module reads."""
    write(tmp_path, "app/db.py", "import sqlalchemy\n")
    write(tmp_path, "app/main.py", "import fastapi\n")

    assert Cartographer(tmp_path).map().context == {}


def test_a_huge_config_file_is_trimmed(tmp_path: Path) -> None:
    write(tmp_path, "docker-compose.yml", "x: 1\n" * 50_000)
    write(tmp_path, "app/db.py", "import sqlalchemy\n")

    context = Cartographer(tmp_path).map().context

    assert len(context["docker-compose.yml"]) < 10_000


def test_a_secret_bearing_file_is_never_collected(tmp_path: Path) -> None:
    """Context is sent to a model and recorded to a cassette that gets
    committed. A .env belongs in neither."""
    write(tmp_path, ".env", "GROQ_API_KEY=gsk_real_secret\n")
    write(tmp_path, "app/db.py", "import sqlalchemy\n")

    assert Cartographer(tmp_path).map().context == {}
