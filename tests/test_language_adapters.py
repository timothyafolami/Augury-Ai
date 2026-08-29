"""One reviewer, six languages.

The practice lab teaches every concern in six languages because the runtime is
what makes the mechanism visible. A reviewer built on that lab that only reads
Python contradicts its own source of knowledge.

Everything above cartography is language-agnostic: the Scheduler, Triage, the
specialists and the Prover all consume `ModuleNode`. These tests pin the
adapter boundary that keeps it that way.
"""

from pathlib import Path

import pytest

from augury.core.cartography import Cartographer, Signal
from augury.core.cartography.languages import Language, adapter_for


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


@pytest.mark.parametrize(
    ("filename", "language"),
    [
        ("a.py", Language.PYTHON),
        ("a.ts", Language.TYPESCRIPT),
        # `.tsx` is TypeScript with JSX and needs the tsx grammar, not typescript.
        ("a.tsx", Language.TSX),
        ("a.js", Language.JAVASCRIPT),
        ("a.go", Language.GO),
        ("a.rs", Language.RUST),
        ("a.java", Language.JAVA),
        ("a.cpp", Language.CPP),
        ("a.hpp", Language.CPP),
    ],
)
def test_recognises_each_language_by_extension(filename: str, language: Language) -> None:
    found = adapter_for(Path(filename))

    assert found is not None
    assert found.language is language


def test_ignores_a_file_in_no_supported_language() -> None:
    assert adapter_for(Path("README.md")) is None


# -- signals, per language -------------------------------------------------
# Same concern, six runtimes. This is the lab's own argument turned into code.


@pytest.mark.parametrize(
    ("filename", "source", "signal"),
    [
        ("svc.go", 'package main\nimport "database/sql"\n', Signal.DATA),
        ("svc.go", 'package main\nimport "net/http"\n', Signal.NETWORK),
        ("svc.go", 'package main\nimport "sync"\n', Signal.CONCURRENCY),
        ("svc.rs", "use tokio::task;\n", Signal.CONCURRENCY),
        ("svc.rs", "use reqwest::Client;\n", Signal.NETWORK),
        ("Svc.java", "import java.sql.Connection;\n", Signal.DATA),
        ("Svc.java", "import java.util.concurrent.Executor;\n", Signal.CONCURRENCY),
        ("svc.ts", "import axios from 'axios';\n", Signal.NETWORK),
        ("svc.ts", "import express from 'express';\n", Signal.ENTRYPOINT),
        ("svc.cpp", "#include <thread>\n", Signal.CONCURRENCY),
    ],
)
def test_detects_a_layer_signal_in_each_runtime(
    tmp_path: Path, filename: str, source: str, signal: Signal
) -> None:
    write(tmp_path, filename, source)

    assert signal in Cartographer(tmp_path).map().module(filename).signals


def test_maps_a_mixed_language_repository_in_one_pass(tmp_path: Path) -> None:
    """A real service is rarely one language. The map is one map."""
    write(tmp_path, "api/main.go", 'package main\nimport "net/http"\n')
    write(tmp_path, "web/app.ts", "import express from 'express';\n")
    write(tmp_path, "jobs/worker.py", "import celery\n")

    repo = Cartographer(tmp_path).map()

    assert {m.path for m in repo.modules} == {"api/main.go", "web/app.ts", "jobs/worker.py"}


def test_counts_lines_in_a_non_python_file(tmp_path: Path) -> None:
    write(tmp_path, "svc.go", 'package main\n\nimport "fmt"\n\nfunc main() {}\n')

    assert Cartographer(tmp_path).map().module("svc.go").loc == 3


def test_a_file_that_does_not_parse_is_recorded_not_fatal(tmp_path: Path) -> None:
    write(tmp_path, "good.go", 'package main\nimport "fmt"\n')
    write(tmp_path, "broken.rs", "fn (((( {\n")

    repo = Cartographer(tmp_path).map()

    assert repo.module("good.go").loc == 2
    assert "broken.rs" in repo.unparsed


def test_detects_a_commonjs_require(tmp_path: Path) -> None:
    """Node code in the wild is still overwhelmingly CommonJS. Handling only
    ESM imports silently reports zero signals for every such file."""
    write(tmp_path, "svc.js", "const http = require('http');\n")

    assert Signal.NETWORK in Cartographer(tmp_path).map().module("svc.js").signals


def test_a_plain_function_call_is_not_treated_as_an_import(tmp_path: Path) -> None:
    """Only `require` counts. Reading every call's string argument would make
    any file mentioning 'redis' in a log line look like a Redis client."""
    write(tmp_path, "svc.js", "log('connecting to redis');\n")

    assert Cartographer(tmp_path).map().module("svc.js").signals == frozenset()


def test_matches_node_prefixed_builtins(tmp_path: Path) -> None:
    """`node:http` and `http` are the same module. Modern Node code prefers
    the prefixed form, and missing it silently zeroes the signal."""
    write(tmp_path, "svc.js", "const http = require('node:http');\n")

    assert Signal.NETWORK in Cartographer(tmp_path).map().module("svc.js").signals


def test_node_crypto_is_a_security_concern(tmp_path: Path) -> None:
    write(tmp_path, "svc.js", "const crypto = require('node:crypto');\n")

    assert Signal.SECURITY in Cartographer(tmp_path).map().module("svc.js").signals
