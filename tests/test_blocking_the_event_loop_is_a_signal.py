"""A synchronous call on a single-threaded runtime is a concurrency concern.

Node runs one thread. A synchronous hash, a synchronous file read or a
synchronous subprocess does not slow the request that made it -- it stops
every other request in the process for the duration, including the health
check. The practice lab puts it this way: Node is the strictest version of
"one blocking call freezes everything."

Nothing routed it anywhere. A TypeScript file whose only defect was
`crypto.pbkdf2Sync` with a million iterations raised `craft` and `data` from
its other lines and never reached the concurrency specialist, so the one
specialist qualified to name the mechanism was never asked.

Found while checking that a TypeScript case would be worth adding: the parser
handled the file correctly and the signal set was still missing the thing the
file was written to demonstrate.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages.source_signals import signals_in_source
from augury.core.cartography.model import Signal

BLOCKING = [
    ("crypto.pbkdf2Sync(pw, salt, 1000000, 64, 'sha512')", "a million-iteration hash"),
    ("const raw = fs.readFileSync(path, 'utf8');", "a synchronous file read"),
    ("execSync('convert in.png out.png');", "a synchronous subprocess"),
    ("const z = zlib.gzipSync(body);", "synchronous compression"),
    ("fs.writeFileSync(dest, JSON.stringify(rows));", "a synchronous write"),
]


@pytest.mark.parametrize("source,why", BLOCKING, ids=[w for _, w in BLOCKING])
@pytest.mark.parametrize("language", ["typescript", "javascript", "tsx"])
def test_a_synchronous_call_raises_concurrency(source: str, why: str, language: str) -> None:
    assert Signal.CONCURRENCY in signals_in_source(language, source), (
        f"{why} blocks the only thread this runtime has"
    )


def test_the_async_form_of_the_same_call_does_not() -> None:
    """Otherwise every file touching fs or crypto routes to concurrency."""
    clean = "const raw = await fs.promises.readFile(path, 'utf8');\nawait pbkdf2(pw, salt);"

    assert Signal.CONCURRENCY not in signals_in_source("typescript", clean)


def test_a_word_merely_ending_in_sync_is_not_a_blocking_call() -> None:
    """`resync`, `sync` and `unsync` are ordinary names, not the Node suffix."""
    ordinary = "await resync(state);\nconst sync = makeSync();\nawait db.sync();"

    assert Signal.CONCURRENCY not in signals_in_source("typescript", ordinary)


@pytest.mark.parametrize("language", ["go", "rust", "java", "cpp", "python"])
def test_the_suffix_means_nothing_off_the_single_threaded_runtimes(language: str) -> None:
    """A Go function named ReadFileSync blocks one goroutine and nothing else.

    The mechanism is the runtime, not the spelling, so the rule is scoped to
    the runtimes where one thread serves every request.
    """
    assert Signal.CONCURRENCY not in signals_in_source(language, "readFileSync(path)")


def test_a_factory_named_make_sync_is_left_alone() -> None:
    """The suffix is a convention user code shares, so the rule names calls.

    Matching every identifier ending in `Sync(` would route a file containing
    an ordinary factory to the concurrency specialist, spending a model call
    to be told nothing.
    """
    ordinary = "const make = makeSync();\nawait resync(state);\nawait db.sync();"

    assert Signal.CONCURRENCY not in signals_in_source("typescript", ordinary)


def test_the_call_is_found_as_a_method_or_destructured() -> None:
    """`fs.readFileSync` and a destructured `readFileSync` both block."""
    for source in ("fs.readFileSync(p)", "const { readFileSync } = fs;\nreadFileSync(p)"):
        assert Signal.CONCURRENCY in signals_in_source("javascript", source)
