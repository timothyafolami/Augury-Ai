"""The import graph is what the Scheduler steers by.

If an edge is missed, fan-in collapses to a constant, the neighbour boost can
never fire, and module selection degenerates to "smallest file with the most
signals". These are the repository shapes that actually occur.
"""

from pathlib import Path

from augury.core.cartography import Cartographer


def write(root: Path, rel: str, source: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


def test_resolves_a_src_layout(tmp_path: Path) -> None:
    """`src/pkg/a.py` is imported as `pkg.a`, not `src.pkg.a`. This is the
    most common modern layout, and it is this project's own."""
    write(tmp_path, "src/pkg/__init__.py")
    write(tmp_path, "src/pkg/store.py", "def fetch() -> None: ...\n")
    write(tmp_path, "src/pkg/routes.py", "from pkg.store import fetch\n")

    repo = Cartographer(tmp_path).map()

    assert "src/pkg/store.py" in repo.module("src/pkg/routes.py").imports
    assert repo.module("src/pkg/store.py").fan_in == 1


def test_resolves_a_relative_import(tmp_path: Path) -> None:
    """`from .store import fetch` is the dominant intra-package idiom."""
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/store.py", "def fetch() -> None: ...\n")
    write(tmp_path, "pkg/routes.py", "from .store import fetch\n")

    repo = Cartographer(tmp_path).map()

    assert "pkg/store.py" in repo.module("pkg/routes.py").imports


def test_resolves_a_bare_relative_package_import(tmp_path: Path) -> None:
    """`from . import store` names the submodule in the alias, not the module."""
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/store.py", "def fetch() -> None: ...\n")
    write(tmp_path, "pkg/routes.py", "from . import store\n")

    repo = Cartographer(tmp_path).map()

    assert "pkg/store.py" in repo.module("pkg/routes.py").imports


def test_resolves_a_parent_relative_import(tmp_path: Path) -> None:
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/store.py")
    write(tmp_path, "pkg/api/__init__.py")
    write(tmp_path, "pkg/api/routes.py", "from ..store import fetch\n")

    repo = Cartographer(tmp_path).map()

    assert "pkg/store.py" in repo.module("pkg/api/routes.py").imports


def test_from_package_import_submodule_credits_the_submodule(tmp_path: Path) -> None:
    """`from pkg import store` depends on store, not on pkg/__init__.py.
    Crediting the package parks blast radius on a signal-less file that will
    never be read, and the neighbour boost then keys on the wrong module."""
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "pkg/store.py")
    write(tmp_path, "pkg/routes.py", "from pkg import store\n")

    repo = Cartographer(tmp_path).map()

    assert "pkg/store.py" in repo.module("pkg/routes.py").imports
    assert repo.module("pkg/store.py").fan_in == 1


def test_from_package_import_name_still_credits_the_package(tmp_path: Path) -> None:
    """When the imported name is a function rather than a module, the package
    really is the dependency."""
    write(tmp_path, "pkg/__init__.py", "def helper() -> None: ...\n")
    write(tmp_path, "pkg/routes.py", "from pkg import helper\n")

    repo = Cartographer(tmp_path).map()

    assert "pkg/__init__.py" in repo.module("pkg/routes.py").imports


def test_a_module_importing_itself_does_not_inflate_its_own_fan_in(tmp_path: Path) -> None:
    """Common in TYPE_CHECKING blocks and re-export shims. A self-edge is not
    blast radius."""
    write(tmp_path, "app/service.py", "import app.service\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("app/service.py").fan_in == 0


def test_augury_can_map_itself(tmp_path: Path) -> None:
    """The honest end-to-end check. A reviewer that cannot see the structure
    of its own repository cannot see anyone else's."""
    repo = Cartographer(Path(__file__).parent.parent).map()

    mapper = repo.module("src/augury/core/cartography/mapper.py")
    assert "src/augury/core/cartography/model.py" in mapper.imports
    assert repo.module("src/augury/core/cartography/model.py").fan_in >= 2


def test_a_package_wins_a_name_collision_with_a_module(tmp_path: Path) -> None:
    """`pkg.py` and `pkg/__init__.py` can coexist. Whichever loses the name
    becomes unreachable as an import target and keeps fan_in=0 forever, so the
    winner is chosen deterministically rather than by iteration order."""
    write(tmp_path, "pkg.py")
    write(tmp_path, "pkg/__init__.py")
    write(tmp_path, "user.py", "import pkg\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("user.py").imports == frozenset({"pkg/__init__.py"})
