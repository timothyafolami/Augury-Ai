"""The two highest-value detectors, in every language the lab teaches.

A swallowed error and an interpolated query are Tier-1 defects with no import
to give them away. Until now only the Python adapter looked for them, so a Go
function discarding an error into `_`, a Java handler catching `Exception` and
returning null, and a TypeScript template literal carrying SQL were all mapped
as ordinary modules. The Scheduler ranks on signals, so those files were never
sent to a specialist at all.

Every snippet here is real code in its language rather than a fragment. The
tree-sitter adapter raises `ParseError` on any tree containing an error node,
so a fixture that is not valid syntax would prove nothing.
"""

from pathlib import Path

import pytest

from augury.core.cartography import Cartographer, Signal


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


def signals_of(root: Path, rel: str) -> frozenset[Signal]:
    return Cartographer(root).map().module(rel).signals


# -- swallowed errors ------------------------------------------------------
# 08-craft/03. The mechanism is the same in every runtime: the failure stops
# propagating, the caller is handed a plausible empty answer, and the incident
# surfaces later somewhere the stack trace cannot reach.


SWALLOWED = [
    pytest.param(
        "store.go",
        'package main\n\nimport "strconv"\n\n'
        "func parse(raw string) int {\n"
        "\tn, _ := strconv.Atoi(raw)\n"
        "\treturn n\n"
        "}\n",
        id="go-error-assigned-to-a-discard",
    ),
    pytest.param(
        "store.go",
        "package main\n\nfunc save(row Row) {\n\t_ = write(row)\n}\n",
        id="go-error-discarded-outright",
    ),
    pytest.param(
        "store.ts",
        "export async function load(id: string) {\n"
        "  try {\n"
        "    return await query(id);\n"
        "  } catch (err) {\n"
        "  }\n"
        "}\n",
        id="typescript-empty-catch",
    ),
    pytest.param(
        "store.js",
        "async function load(id) {\n"
        "  try {\n"
        "    return await query(id);\n"
        "  } catch (err) {\n"
        "    return [];\n"
        "  }\n"
        "}\n",
        id="javascript-catch-returning-empty",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String load(String id) {\n"
        "        try {\n"
        "            return query(id);\n"
        "        } catch (Exception e) {\n"
        "            return null;\n"
        "        }\n"
        "    }\n"
        "}\n",
        id="java-broad-catch-returning-null",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    void run() {\n"
        "        try {\n"
        "            work();\n"
        "        } catch (Throwable t) {\n"
        "        }\n"
        "    }\n"
        "}\n",
        id="java-catch-throwable",
    ),
    pytest.param(
        "store.cpp",
        "#include <string>\n\n"
        "std::string load(const std::string& id) {\n"
        "    try {\n"
        "        return query(id);\n"
        "    } catch (...) {\n"
        "    }\n"
        '    return "";\n'
        "}\n",
        id="cpp-catch-all",
    ),
    pytest.param(
        "store.rs",
        "fn load(id: &str) -> String {\n    let row = query(id).unwrap();\n    row.name\n}\n",
        id="rust-unwrap",
    ),
    pytest.param(
        "store.rs",
        "fn load(id: &str) -> String {\n"
        '    let row = query(id).expect("row must exist");\n'
        "    row.name\n"
        "}\n",
        id="rust-expect",
    ),
]


@pytest.mark.parametrize(("filename", "source"), SWALLOWED)
def test_flags_craft_where_an_error_is_swallowed(
    tmp_path: Path, filename: str, source: str
) -> None:
    write(tmp_path, filename, source)

    assert Signal.CRAFT in signals_of(tmp_path, filename)


HANDLED = [
    pytest.param(
        "store.go",
        "package main\n\nfunc load() error {\n\t_, err := read()\n\treturn err\n}\n",
        id="go-discards-the-value-and-keeps-the-error",
    ),
    pytest.param(
        "store.go",
        "package main\n\n"
        "func total(items []int) int {\n"
        "\tsum := 0\n"
        "\tfor _, item := range items {\n"
        "\t\tsum += item\n"
        "\t}\n"
        "\treturn sum\n"
        "}\n",
        id="go-blank-identifier-in-a-range-clause",
    ),
    pytest.param(
        "store.ts",
        "export async function load(id: string) {\n"
        "  try {\n"
        "    return await query(id);\n"
        "  } catch (err) {\n"
        "    record(err);\n"
        "    throw err;\n"
        "  }\n"
        "}\n",
        id="typescript-catch-that-rethrows",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String load(String id) {\n"
        "        try {\n"
        "            return query(id);\n"
        "        } catch (Exception e) {\n"
        "            throw new IllegalStateException(e);\n"
        "        }\n"
        "    }\n"
        "}\n",
        id="java-broad-catch-that-rethrows",
    ),
    pytest.param(
        "Store.java",
        "import java.io.IOException;\n\n"
        "class Store {\n"
        "    String load(String id) {\n"
        "        try {\n"
        "            return query(id);\n"
        "        } catch (IOException e) {\n"
        '            return "";\n'
        "        }\n"
        "    }\n"
        "}\n",
        id="java-narrow-catch",
    ),
    pytest.param(
        "store.cpp",
        "#include <string>\n\n"
        "std::string load(const std::string& id) {\n"
        "    try {\n"
        "        return query(id);\n"
        "    } catch (const std::exception& e) {\n"
        "        throw;\n"
        "    }\n"
        "}\n",
        id="cpp-catch-that-rethrows",
    ),
    pytest.param(
        "store.rs",
        "fn load(id: &str) -> Result<Row, Error> {\n    let row = query(id)?;\n    Ok(row)\n}\n",
        id="rust-question-mark-propagates",
    ),
]


@pytest.mark.parametrize(("filename", "source"), HANDLED)
def test_does_not_flag_an_error_that_is_propagated(
    tmp_path: Path, filename: str, source: str
) -> None:
    """Flagging correct code trains its user to ignore the reviewer, and each
    false signal spends a real model call on a file with nothing to say."""
    write(tmp_path, filename, source)

    assert Signal.CRAFT not in signals_of(tmp_path, filename)


# -- interpolated queries --------------------------------------------------
# 07-security/02. The query text is assembled before the driver sees it, so
# the driver has no parameter to escape and the input becomes syntax.


INTERPOLATED = [
    pytest.param(
        "store.go",
        'package main\n\nimport "fmt"\n\n'
        "func find(name string) string {\n"
        "\treturn fmt.Sprintf(\"SELECT * FROM users WHERE name = '%s'\", name)\n"
        "}\n",
        id="go-sprintf",
    ),
    pytest.param(
        "store.go",
        "package main\n\n"
        "func find(name string) string {\n"
        '\treturn "SELECT * FROM users WHERE name = " + name\n'
        "}\n",
        id="go-concatenation",
    ),
    pytest.param(
        "store.ts",
        "export function find(name: string) {\n"
        "  return run(`SELECT * FROM users WHERE name = '${name}'`);\n"
        "}\n",
        id="typescript-template-literal",
    ),
    pytest.param(
        "store.js",
        "function find(name) {\n  return run('SELECT * FROM users WHERE name = ' + name);\n}\n",
        id="javascript-concatenation",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String find(String name) {\n"
        '        return "SELECT * FROM users WHERE name = " + name;\n'
        "    }\n"
        "}\n",
        id="java-concatenation",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String find(String name) {\n"
        "        return String.format(\"DELETE FROM users WHERE name = '%s'\", name);\n"
        "    }\n"
        "}\n",
        id="java-string-format",
    ),
    pytest.param(
        "store.rs",
        "fn find(name: &str) -> String {\n"
        "    format!(\"SELECT * FROM users WHERE name = '{}'\", name)\n"
        "}\n",
        id="rust-format-macro",
    ),
    pytest.param(
        "store.cpp",
        "#include <string>\n\n"
        "std::string find(const std::string& name) {\n"
        '    return std::string("SELECT * FROM users WHERE name = ") + name;\n'
        "}\n",
        id="cpp-concatenation",
    ),
]


@pytest.mark.parametrize(("filename", "source"), INTERPOLATED)
def test_flags_security_and_data_where_a_query_is_interpolated(
    tmp_path: Path, filename: str, source: str
) -> None:
    signals = signals_of(tmp_path, filename)

    assert Signal.SECURITY in signals
    assert Signal.DATA in signals


def _written(tmp_path: Path, filename: str, source: str) -> frozenset[Signal]:
    write(tmp_path, filename, source)
    return signals_of(tmp_path, filename)


@pytest.fixture(autouse=True)
def _write_the_parametrised_source(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """Parametrised cases carry their own source; write it before the test."""
    params = getattr(request.node, "callspec", None)
    if params is None:
        return
    filename = params.params.get("filename")
    source = params.params.get("source")
    if filename is not None and source is not None:
        write(tmp_path, filename, source)


PARAMETERISED = [
    pytest.param(
        "store.go",
        "package main\n\n"
        "func find(db DB, name string) Rows {\n"
        '\treturn db.Query("SELECT * FROM users WHERE name = $1", name)\n'
        "}\n",
        id="go-placeholder-is-passed-to-the-driver",
    ),
    pytest.param(
        "store.ts",
        "export function find(name: string) {\n"
        "  return db.query('SELECT * FROM users WHERE name = $1', [name]);\n"
        "}\n",
        id="typescript-placeholder-is-passed-to-the-driver",
    ),
    pytest.param(
        "store.ts",
        "export function all() {\n"
        "  return db.query(`SELECT id, name FROM users ORDER BY id`);\n"
        "}\n",
        id="typescript-template-literal-with-no-substitution",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String find() {\n"
        '        return "SELECT * FROM users WHERE name = ?";\n'
        "    }\n"
        "}\n",
        id="java-placeholder-is-passed-to-the-driver",
    ),
    pytest.param(
        "store.rs",
        "fn find(name: &str) -> Query {\n"
        '    sqlx::query("SELECT * FROM users WHERE name = $1").bind(name)\n'
        "}\n",
        id="rust-placeholder-is-passed-to-the-driver",
    ),
]


@pytest.mark.parametrize(("filename", "source"), PARAMETERISED)
def test_does_not_flag_a_parameterised_query(tmp_path: Path, filename: str, source: str) -> None:
    """A placeholder reaches the driver as a placeholder, so the value is
    bound rather than pasted and there is nothing for a specialist to see."""
    assert Signal.SECURITY not in signals_of(tmp_path, filename)


PROSE = [
    pytest.param(
        "store.go",
        'package main\n\nimport "fmt"\n\n'
        "func report(user string, n int) string {\n"
        '\treturn fmt.Sprintf("update failed for %s after %d attempts", user, n)\n'
        "}\n",
        id="go-log-line-naming-an-update",
    ),
    pytest.param(
        "store.ts",
        "export function report(user: string, n: number) {\n"
        "  return `delete of ${user} failed after ${n} attempts`;\n"
        "}\n",
        id="typescript-log-line-naming-a-delete",
    ),
    pytest.param(
        "Store.java",
        "class Store {\n"
        "    String report(String user) {\n"
        '        return "could not update record for " + user;\n'
        "    }\n"
        "}\n",
        id="java-log-line-naming-an-update",
    ),
]


@pytest.mark.parametrize(("filename", "source"), PROSE)
def test_does_not_flag_prose_carrying_a_bare_sql_word(
    tmp_path: Path, filename: str, source: str
) -> None:
    """The detector matches co-occurring uppercase keywords, so English prose
    that happens to contain "update" or "delete" stays silent."""
    assert Signal.SECURITY not in signals_of(tmp_path, filename)
