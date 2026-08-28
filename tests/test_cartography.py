"""The Cartographer is the map the Scheduler steers by, and it uses no model.

Everything here is deterministic: an AST walk, an import graph and git churn.
If this layer is wrong, every downstream agent is reading a bad map.
"""

from pathlib import Path

from augury.core.cartography import Cartographer, Signal


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


def test_records_each_module_with_its_line_count(tmp_path: Path) -> None:
    write(tmp_path, "app/service.py", "x = 1\ny = 2\nz = 3\n")

    repo = Cartographer(tmp_path).map()

    module = repo.module("app/service.py")
    assert module.loc == 3


def test_records_imports_between_modules_in_the_repo(tmp_path: Path) -> None:
    write(tmp_path, "app/routes.py", "from app.store import fetch\n")
    write(tmp_path, "app/store.py", "def fetch() -> None: ...\n")

    repo = Cartographer(tmp_path).map()

    assert "app/store.py" in repo.module("app/routes.py").imports


def test_ignores_imports_of_third_party_packages(tmp_path: Path) -> None:
    write(tmp_path, "app/routes.py", "import httpx\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("app/routes.py").imports == frozenset()


def test_fan_in_counts_modules_that_depend_on_this_one(tmp_path: Path) -> None:
    write(tmp_path, "app/store.py", "def fetch() -> None: ...\n")
    write(tmp_path, "app/routes.py", "from app.store import fetch\n")
    write(tmp_path, "app/tasks.py", "from app.store import fetch\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("app/store.py").fan_in == 2
    assert repo.module("app/routes.py").fan_in == 0


def test_flags_concurrency_where_shared_state_is_touched_from_threads(tmp_path: Path) -> None:
    write(tmp_path, "app/counter.py", "import threading\n\nlock = threading.Lock()\n")

    repo = Cartographer(tmp_path).map()

    assert Signal.CONCURRENCY in repo.module("app/counter.py").signals


def test_flags_data_access_on_orm_session_use(tmp_path: Path) -> None:
    write(tmp_path, "app/store.py", "from sqlalchemy.orm import Session\n")

    repo = Cartographer(tmp_path).map()

    assert Signal.DATA in repo.module("app/store.py").signals


def test_flags_an_http_client_as_a_network_boundary(tmp_path: Path) -> None:
    write(tmp_path, "app/client.py", "import httpx\n")

    repo = Cartographer(tmp_path).map()

    assert Signal.NETWORK in repo.module("app/client.py").signals


def test_flags_a_route_handler_as_an_entrypoint(tmp_path: Path) -> None:
    write(tmp_path, "app/api.py", "from fastapi import FastAPI\napp = FastAPI()\n")

    repo = Cartographer(tmp_path).map()

    assert Signal.ENTRYPOINT in repo.module("app/api.py").signals


def test_a_module_with_no_recognised_signal_carries_none(tmp_path: Path) -> None:
    """Signals must be evidence, not decoration. A plain module gets nothing,
    so Triage does not fan out to eight specialists on an empty file."""
    write(tmp_path, "app/constants.py", "TIMEOUT_DEFAULT = 30\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("app/constants.py").signals == frozenset()


def test_skips_virtualenvs_and_caches(tmp_path: Path) -> None:
    write(tmp_path, "app/service.py", "x = 1\n")
    write(tmp_path, ".venv/lib/site-packages/numpy/core.py", "x = 1\n")
    write(tmp_path, "__pycache__/service.py", "x = 1\n")

    repo = Cartographer(tmp_path).map()

    assert [m.path for m in repo.modules] == ["app/service.py"]


def test_a_file_that_does_not_parse_does_not_sink_the_map(tmp_path: Path) -> None:
    """Real repositories contain broken files. Mapping is best-effort and
    records the failure rather than aborting the review."""
    write(tmp_path, "app/good.py", "x = 1\n")
    write(tmp_path, "app/broken.py", "def (((\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("app/good.py").loc == 1
    assert "app/broken.py" in repo.unparsed
