"""Starting a thread is a concurrency concern in every language that can.

Signals for the compiled languages come off the import list, and the import
list is the wrong place to look for this. `go func() { ... }()` imports
nothing. `synchronized` imports nothing. `std::thread` needs `<thread>`, but a
file that already includes it for another reason gets no credit for the line
that actually spawns.

Measured, not supposed. `internal/reindex/worker.go` in the Go case exists to
demonstrate a goroutine leak -- unbuffered channels, one goroutine per item,
an early return that strands every sender -- and it raised `data` and
`observability`. The concurrency specialist, the one qualified to name that
mechanism, was never asked to read it.

Layer 1 of the practice lab is concurrency across six languages. This is the
detector that claim needs.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages.source_signals import signals_in_source
from augury.core.cartography.model import Signal

SPAWNS = [
    ("go", "go func(sku string) { results <- price(sku) }(it.SKU)", "goroutine literal"),
    ("go", "go worker(jobs, results)", "goroutine call"),
    ("go", "results := make(chan Result)", "channel"),
    ("go", "var mu sync.Mutex", "mutex"),
    ("java", "synchronized (this) { total += amount; }", "synchronized block"),
    ("java", "ExecutorService pool = Executors.newFixedThreadPool(8);", "executor"),
    ("java", "new Thread(() -> work()).start();", "thread"),
    ("java", "CompletableFuture.supplyAsync(() -> fetch());", "future"),
    ("cpp", "std::thread worker(run); worker.detach();", "detached thread"),
    ("cpp", "std::mutex guard;", "mutex"),
    ("cpp", "std::atomic<int> counter{0};", "atomic"),
    ("cpp", "pthread_create(&t, nullptr, run, nullptr);", "pthread"),
    ("rust", "let handle = thread::spawn(move || work());", "thread spawn"),
    ("rust", "tokio::spawn(async move { serve().await });", "task spawn"),
    ("rust", "let shared = Arc::new(Mutex::new(0));", "arc mutex"),
    ("rust", "let lock = RwLock::new(state);", "rwlock"),
]

QUIET = [
    ("go", 'fmt.Println("go to the next page")', "the word go in a string"),
    ("go", "// go through the list and total it", "the word go in a comment"),
    ("java", "int channel = 4;", "a variable called channel"),
    ("cpp", "int threads = count();", "a variable called threads"),
    ("rust", "let arc = compute_arc(radius);", "a function called compute_arc"),
    ("python", "go_home()", "python, which has its own detector"),
]


@pytest.mark.parametrize("language,source,why", SPAWNS, ids=[f"{a}-{c}" for a, _, c in SPAWNS])
def test_a_concurrency_primitive_raises_concurrency(language: str, source: str, why: str) -> None:
    assert Signal.CONCURRENCY in signals_in_source(language, source), (
        f"{why}: the specialist that can name this mechanism is chosen by signal"
    )


@pytest.mark.parametrize("language,source,why", QUIET, ids=[f"{a}-{c}" for a, _, c in QUIET])
def test_ordinary_code_does_not_raise_concurrency(language: str, source: str, why: str) -> None:
    """Routing a file to a specialist costs a model call. A detector that
    fires on the word "go" in a sentence spends money to be told nothing."""
    assert Signal.CONCURRENCY not in signals_in_source(language, source), why


def test_the_worker_that_leaks_goroutines_is_routed_to_concurrency() -> None:
    """The case this was found in, asserted end to end."""
    from pathlib import Path

    from augury.core.cartography.mapper import Cartographer

    repo = Path("eval/cases/E01-go-inventory/repo")
    if not repo.is_dir():  # pragma: no cover - the case ships with the repository
        pytest.skip("the Go case is missing")

    found = {module.path: module.signals for module in Cartographer(repo).map().modules}

    assert Signal.CONCURRENCY in found["internal/reindex/worker.go"]
