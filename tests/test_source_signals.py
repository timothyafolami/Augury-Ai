"""Some concerns have no import to give them away.

A swallowed exception, an interpolated query and shared mutable state are all
invisible to an import table, and all three are Tier-1 defects in the taxonomy.
If the Cartographer cannot see them, the Scheduler never reads those modules
and the specialists never get a chance.
"""

from pathlib import Path

from augury.core.cartography import Cartographer, Signal


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


def test_flags_craft_where_an_exception_is_swallowed(tmp_path: Path) -> None:
    """08-craft/03: a swallowed exception turns a broken database into a fast,
    successful, empty response."""
    write(
        tmp_path,
        "app/store.py",
        "def fetch():\n"
        "    try:\n"
        "        return query()\n"
        "    except Exception:\n"
        "        return []\n",
    )

    repo = Cartographer(tmp_path).map()

    assert Signal.CRAFT in repo.module("app/store.py").signals


def test_does_not_flag_an_exception_that_is_handled_and_re_raised(tmp_path: Path) -> None:
    """Handling an error and re-raising it is the correct pattern. Flagging it
    would train the user to ignore the reviewer."""
    write(
        tmp_path,
        "app/store.py",
        "def fetch():\n"
        "    try:\n"
        "        return query()\n"
        "    except ValueError:\n"
        "        log()\n"
        "        raise\n",
    )

    repo = Cartographer(tmp_path).map()

    assert Signal.CRAFT not in repo.module("app/store.py").signals


def test_flags_security_where_a_query_is_built_by_interpolation(tmp_path: Path) -> None:
    """07-security/02: the injection is in the string, not in the import."""
    write(
        tmp_path,
        "app/admin.py",
        "def search(term):\n    return execute(f'SELECT * FROM users WHERE name = {term}')\n",
    )

    signals = Cartographer(tmp_path).map().module("app/admin.py").signals

    assert Signal.SECURITY in signals
    assert Signal.DATA in signals


def test_does_not_flag_a_parameterised_query(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/admin.py",
        "def search(term):\n"
        "    return execute('SELECT * FROM users WHERE name = :name', name=term)\n",
    )

    assert Signal.SECURITY not in Cartographer(tmp_path).map().module("app/admin.py").signals


def test_flags_concurrency_where_module_state_is_mutated_in_a_function(tmp_path: Path) -> None:
    """01-machine/04: shared mutable state touched from more than one place
    corrupts silently, sometimes, some of the time."""
    write(
        tmp_path,
        "app/counter.py",
        "seen = 0\n\n\ndef record():\n    global seen\n    seen += 1\n",
    )

    repo = Cartographer(tmp_path).map()

    assert Signal.CONCURRENCY in repo.module("app/counter.py").signals


def test_flags_percent_formatted_queries_too(tmp_path: Path) -> None:
    """The oldest injection vector in the language, and still the most common
    in code that predates f-strings."""
    write(
        tmp_path,
        "app/legacy.py",
        "def search(term):\n    return execute('SELECT * FROM users WHERE name = %s' % term)\n",
    )

    assert Signal.SECURITY in Cartographer(tmp_path).map().module("app/legacy.py").signals


# -- false positives -------------------------------------------------------
# The detector uppercased its input before matching, which made it
# case-insensitive against English prose. "a false signal costs a real model
# call" is the module's own rule, so these must stay silent.


def test_does_not_flag_an_ordinary_log_message(tmp_path: Path) -> None:
    write(tmp_path, "app/net.py", 'def go(n, url):\n    log(f"downloaded {n} bytes from {url}")\n')

    assert Cartographer(tmp_path).map().module("app/net.py").signals == frozenset()


def test_does_not_flag_prose_containing_a_bare_sql_word(tmp_path: Path) -> None:
    write(tmp_path, "app/msg.py", 'def go(u):\n    log(f"update failed for {u}")\n')

    assert Signal.SECURITY not in Cartographer(tmp_path).map().module("app/msg.py").signals


# -- other interpolation shapes -------------------------------------------


def test_flags_a_query_built_with_format(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/f.py",
        "def s(t):\n    return execute('SELECT * FROM users WHERE n = {}'.format(t))\n",
    )

    assert Signal.SECURITY in Cartographer(tmp_path).map().module("app/f.py").signals


def test_flags_a_query_built_by_concatenation(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/c.py",
        "def s(t):\n    return execute('SELECT * FROM users WHERE n = ' + t)\n",
    )

    assert Signal.SECURITY in Cartographer(tmp_path).map().module("app/c.py").signals


# -- swallowed exceptions: the shapes the first pass missed ----------------


def test_flags_a_tuple_handler_containing_a_broad_exception(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/t.py",
        "def f():\n    try:\n        g()\n    except (ValueError, Exception):\n        pass\n",
    )

    assert Signal.CRAFT in Cartographer(tmp_path).map().module("app/t.py").signals


def test_flags_a_qualified_broad_exception(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/q.py",
        "import builtins\n\n\ndef f():\n"
        "    try:\n        g()\n    except builtins.Exception:\n        pass\n",
    )

    assert Signal.CRAFT in Cartographer(tmp_path).map().module("app/q.py").signals


def test_a_raise_inside_a_nested_function_does_not_count_as_re_raising(tmp_path: Path) -> None:
    """The handler still swallows. The nested function may never be called."""
    write(
        tmp_path,
        "app/n.py",
        "def f():\n    try:\n        g()\n    except Exception:\n"
        "        def helper():\n            raise ValueError()\n        return []\n",
    )

    assert Signal.CRAFT in Cartographer(tmp_path).map().module("app/n.py").signals


def test_a_raise_in_a_nested_handler_does_not_count_as_re_raising(tmp_path: Path) -> None:
    """Re-raising a different, narrower error from cleanup still loses the
    original failure."""
    write(
        tmp_path,
        "app/i.py",
        "def f():\n    try:\n        g()\n    except Exception:\n"
        "        try:\n            cleanup()\n        except OSError:\n            raise\n"
        "        return []\n",
    )

    assert Signal.CRAFT in Cartographer(tmp_path).map().module("app/i.py").signals
