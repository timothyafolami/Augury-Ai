"""What the map refuses to contain, and what it admits about the refusal.

Two claims live here, and both are load-bearing for a reviewer nobody watches.

The first is that a .env is never read. A repository under review is
attacker-controlled whenever the attacker wants it to be, its .env holds live
credentials for that repository, and everything the mapper collects reaches a
model and then a cassette that gets committed. Today a .env survives only
because no adapter claims its suffix, which is an accident rather than a
decision -- the next person to register an extension undoes it, silently and
in one line. These tests register the suffix themselves and demand the file
stay out anyway. `.env.example` and `.env.sample` are the exception, because
they are committed and hold no value worth stealing.

The second is that the map states what it dropped. A large repository excludes
far more than it includes, and nothing recorded that: the map carried
`unreachable` and the scheduler carried `skipped`, but the vendored trees,
installed environments and build output that never entered the map were simply
gone. A tool whose whole claim is that it reports what it did not look at
cannot be silent about most of the repository. What it records is a reason and
a count per category, never the paths -- 40,000 vendored files must produce one
line, not 40,000.
"""

from pathlib import Path

import pytest

from augury.core.cartography import Cartographer
from augury.core.cartography.languages import EXTENSIONS, Language

# Shaped like a real key so a leak is unmistakable, and unique so it can be
# searched for across the whole serialised map rather than field by field.
LIVE_KEY = "gsk_live_2f8b41c7d90e4a63b5f1c8d27ae0934b"

DOTENV = f"GROQ_API_KEY={LIVE_KEY}\nDATABASE_URL=postgres://u:hunter2@db:5432/app\n"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def suffixes_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register every suffix a dotenv wears, as the next person might.

    Without this the tests below prove nothing: `.env` has no suffix any
    adapter claims, so it is filtered out by a table that was never written
    with secrets in mind. Registering the suffixes removes that accident and
    leaves only a deliberate rule to pass or fail.
    """
    for suffix in ("", ".env", ".local", ".production"):
        monkeypatch.setitem(EXTENSIONS, suffix, Language.PYTHON)


# -- a .env is never read, mapped, or carried into a prompt ------------------


def test_a_live_key_in_a_dotenv_reaches_no_part_of_the_map(
    tmp_path: Path, suffixes_registered: None
) -> None:
    """One assertion over the whole serialised map, not one per field.

    A per-field check passes until somebody adds a field. The secret is
    unique, so searching the entire document is the claim actually wanted:
    nothing that leaves this object carries the key.

    The path is checked too, and not out of tidiness. Recording `.env` in
    `unparsed` reads as honest and is worse than silence: it tells a model
    that a .env sits at that path, and symbol location will read any
    repo-relative path a model names.
    """
    write(tmp_path, ".env", DOTENV)
    write(tmp_path, "app/main.py", "import fastapi\n")

    mapped = Cartographer(tmp_path).map()

    assert LIVE_KEY not in mapped.model_dump_json()
    assert ".env" not in mapped.model_dump_json()
    assert [module.path for module in mapped.modules] == ["app/main.py"]


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production", ".envrc", "config.env"])
def test_a_dotenv_is_excluded_by_name_rather_than_by_extension(
    tmp_path: Path, suffixes_registered: None, name: str
) -> None:
    """Every shape of the file, with its suffix registered as source.

    `.env.local` and `.env.production` are what a real service ships, and a
    rule that only knows the bare name leaks both.
    """
    write(tmp_path, name, DOTENV)
    write(tmp_path, "app/main.py", "import fastapi\n")

    mapped = Cartographer(tmp_path).map()

    document = mapped.model_dump_json()
    assert LIVE_KEY not in document
    assert name not in document


def test_a_dotenv_is_never_opened_while_its_template_still_is(
    tmp_path: Path, suffixes_registered: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not read, not merely absent from the output.

    Excluding a file from the result is weaker than never opening it: a read
    that happens and is then discarded still pulls the secret into this
    process, where a traceback or a debug log can carry it out.
    """
    opened: list[str] = []
    read_text = Path.read_text

    def recording(self: Path, encoding: str | None = None, errors: str | None = None) -> str:
        opened.append(self.name)
        return read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", recording)

    write(tmp_path, ".env", DOTENV)
    write(tmp_path, ".env.local", DOTENV)
    write(tmp_path, ".env.example", "GROQ_API_KEY=\nDATABASE_URL=\n")
    write(tmp_path, "app/main.py", "import fastapi\n")

    Cartographer(tmp_path).map()

    assert [name for name in opened if name.startswith(".env")] == [".env.example"]


def test_the_committed_templates_stay_visible(tmp_path: Path) -> None:
    """A template names the variables the code reads and holds none of them.

    That is exactly the ambient configuration a defect hides in -- a pool size
    declared here against a worker count declared in the Dockerfile -- so
    excluding it to be safe would cost a real class of finding for nothing.
    """
    write(tmp_path, ".env.example", "DB_POOL_SIZE=5\nGROQ_API_KEY=\n")
    write(tmp_path, ".env.sample", "DB_POOL_SIZE=5\n")
    write(tmp_path, "app/db.py", "import sqlalchemy\n")

    context = Cartographer(tmp_path).map().context

    assert "DB_POOL_SIZE=5" in context[".env.example"]
    assert ".env.sample" in context


def test_a_refused_dotenv_is_counted_rather_than_silently_dropped(
    tmp_path: Path, suffixes_registered: None
) -> None:
    """Refusing to read it is right. Refusing to mention it is not."""
    write(tmp_path, ".env", DOTENV)
    write(tmp_path, ".env.production", DOTENV)
    write(tmp_path, "app/main.py", "import fastapi\n")

    excluded = Cartographer(tmp_path).map().excluded

    assert excluded["secrets"].count == 2
    assert LIVE_KEY not in excluded["secrets"].reason


# -- the map states what never entered it -----------------------------------


def test_names_each_excluded_category_with_a_count(tmp_path: Path) -> None:
    write(tmp_path, "app/main.py", "import fastapi\n")
    for index in range(3):
        write(tmp_path, f"node_modules/left-pad/index{index}.js", "module.exports = 1;\n")
    write(tmp_path, "vendor/copied.py", "x = 1\n")
    write(tmp_path, "third_party/copied.py", "x = 1\n")
    write(tmp_path, "generated/client.py", "x = 1\n")
    write(tmp_path, "app/static/vendor.min.js", "var a=1;\n")
    write(tmp_path, "testdata/sample.py", "x = 1\n")
    write(tmp_path, "README.md", "# service\n")

    excluded = Cartographer(tmp_path).map().excluded

    assert excluded["node_modules"].count == 3
    assert excluded["vendor"].count == 1
    assert excluded["third_party"].count == 1
    assert excluded["generated"].count == 1
    assert excluded["minified"].count == 1
    assert excluded["fixtures"].count == 1
    assert excluded["unsupported"].count == 1


def test_states_a_reason_for_every_category_it_counts(tmp_path: Path) -> None:
    """A count without a reason is a number nobody can act on."""
    write(tmp_path, "app/main.py", "import fastapi\n")
    write(tmp_path, "node_modules/left-pad/index.js", "module.exports = 1;\n")
    write(tmp_path, ".venv/lib/site.py", "x = 1\n")
    write(tmp_path, "build/out.js", "var a=1;\n")
    write(tmp_path, "README.md", "# service\n")

    excluded = Cartographer(tmp_path).map().excluded

    assert set(excluded) >= {"node_modules", ".venv", "build", "unsupported"}
    for category, entry in excluded.items():
        assert entry.reason.strip(), f"{category} is counted without a reason"
        assert entry.count > 0, f"{category} is listed with nothing in it"


def test_counts_rather_than_lists_so_a_vendored_tree_stays_one_line(tmp_path: Path) -> None:
    """The point of the count. A repository with 40,000 excluded files must
    not produce a 40,000-entry list, or the honesty is unreadable and the
    document that carries it stops fitting anywhere."""
    write(tmp_path, "app/main.py", "import fastapi\n")
    for index in range(40):
        write(tmp_path, f"node_modules/pkg/module{index}.js", "module.exports = 1;\n")

    mapped = Cartographer(tmp_path).map()

    assert mapped.excluded["node_modules"].count == 40
    assert "module17.js" not in mapped.model_dump_json()


def test_a_repository_with_nothing_excluded_claims_nothing(tmp_path: Path) -> None:
    """Zero-count entries would make every map look like it dropped things."""
    write(tmp_path, "app/main.py", "import fastapi\n")

    assert Cartographer(tmp_path).map().excluded == {}


def test_files_outside_the_requested_scope_are_counted_not_forgotten(tmp_path: Path) -> None:
    """Scope is the reviewer's own choice, and still the largest thing it did
    not read. A run scoped to one service must say so rather than read as a
    review of the repository."""
    write(tmp_path, "backend/main.py", "import fastapi\n")
    write(tmp_path, "frontend/app.ts", "export const a = 1;\n")
    write(tmp_path, "frontend/store.ts", "export const b = 2;\n")

    excluded = Cartographer(tmp_path, scope=("backend",)).map().excluded

    assert excluded["out_of_scope"].count == 2


def test_every_file_in_the_repository_lands_in_exactly_one_bucket(tmp_path: Path) -> None:
    """The arithmetic behind the claim.

    Mapped, skipped, unparsed or excluded. A file in none of them was dropped
    by nobody's decision, which is the failure the whole ledger exists to make
    impossible -- and it is the only check that stays true as categories are
    added, because it counts the repository rather than the rules.
    """
    write(tmp_path, "app/main.py", "import fastapi\n")
    write(tmp_path, "app/db.py", "import sqlalchemy\n")
    write(tmp_path, "tests/test_db.py", "def test_it() -> None: ...\n")
    write(tmp_path, "app/broken.py", "def (\n")
    write(tmp_path, "node_modules/pkg/index.js", "module.exports = 1;\n")
    write(tmp_path, "README.md", "# service\n")
    write(tmp_path, ".env", DOTENV)

    mapped = Cartographer(tmp_path).map()

    accounted = (
        len(mapped.modules)
        + len(mapped.skipped)
        + len(mapped.unparsed)
        + sum(entry.count for entry in mapped.excluded.values())
    )
    assert accounted == sum(1 for path in tmp_path.rglob("*") if path.is_file())
