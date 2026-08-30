"""In TypeScript the network call has no import to detect.

Signals for non-Python languages are read off the import list. That works for
`requests` in Python and `net/http` in Go, and it fails completely for the
call modern TypeScript actually makes: `fetch` is a global. A module whose
only job is to call an upstream service therefore raised no signal at all, no
specialist was qualified to read it, and the scheduler had no reason to.

Measured, not supposed: in the TypeScript case `src/lib/pricing.ts` reported
an empty signal set, went unread, and its seeded defect -- a fetch with no
timeout -- was the one the review missed.

The same argument covers the other globals a browser-shaped runtime provides
without an import.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages.source_signals import signals_in_source
from augury.core.cartography.model import Signal

NETWORK_CALLS = [
    'await fetch("http://pricing:9000/quote")',
    "const res = await fetch(url, { method: 'POST' });",
    "new WebSocket('wss://example.com/feed')",
    "navigator.sendBeacon('/metrics', body)",
    "const es = new EventSource('/stream');",
]


@pytest.mark.parametrize("source", NETWORK_CALLS, ids=lambda s: s[:24])
@pytest.mark.parametrize("language", ["typescript", "javascript", "tsx"])
def test_a_global_network_call_raises_network(source: str, language: str) -> None:
    assert Signal.NETWORK in signals_in_source(language, source), (
        "the call has no import, so nothing else can see it"
    )


def test_a_method_named_fetch_is_not_the_global(tmp_path_factory: pytest.TempPathFactory) -> None:
    """`repo.fetch(id)` and `this.fetch()` are ordinary names.

    Treating them as network calls would route every repository class to the
    network specialist, which spends a model call to be told nothing.
    """
    ordinary = "const row = await repo.fetch(id);\nthis.fetch();\nconst f = obj.fetch;"

    assert Signal.NETWORK not in signals_in_source("typescript", ordinary)


def test_the_word_fetch_in_prose_is_not_a_call() -> None:
    """A comment explaining that something fetches is not a fetch."""
    prose = "// fetch the row, then fetch the price\nconst x = 1;"

    assert Signal.NETWORK not in signals_in_source("typescript", prose)


@pytest.mark.parametrize("language", ["go", "rust", "java", "cpp", "python"])
def test_the_rule_is_scoped_to_the_runtimes_that_have_these_globals(language: str) -> None:
    """Python's `fetch(` is somebody's function, not an HTTP call."""
    assert Signal.NETWORK not in signals_in_source(language, "fetch(url)")
