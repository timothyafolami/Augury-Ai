"""How much the query cache retains after a realistic spread of queries.

Offers the case repository's own cache a wide spread of distinct queries and
reports the bytes it is still holding afterwards. A bounded cache retains its
bound; an unbounded one retains everything it was ever asked.

The measurement walks the structure with `sys.getsizeof` rather than sampling
the process RSS. RSS moves with the allocator, the garbage collector and
whatever else the interpreter is doing, and an earlier experiment in this
project reported a number that turned out to be CPython's GC rather than the
code under test. Summing the retained objects is deterministic for the same
input, which is the property that matters here.

The last line printed is the measurement, in bytes.
"""

import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from app.index import cache  # noqa: E402

DISTINCT_QUERIES = 2_000
RESULTS_PER_QUERY = 5


def retained() -> int:
    """Bytes held by the cache: its own table, plus every key and value in it."""
    entries = getattr(cache, "_entries", None)
    if entries is None:  # pragma: no cover - the remediation renames nothing
        raise SystemExit("cache exposes no entry table; the experiment is wrong, not the code")

    total = sys.getsizeof(entries)
    items = entries.items() if hasattr(entries, "items") else []
    for key, value in items:
        total += sys.getsizeof(key) + sys.getsizeof(value)
        for row in value:
            total += sys.getsizeof(row)
            for field, held in row.items():
                total += sys.getsizeof(field) + sys.getsizeof(held)
    return total


def main() -> None:
    cache.clear()
    print(f"offering {DISTINCT_QUERIES} distinct queries, {RESULTS_PER_QUERY} results each")

    for index in range(DISTINCT_QUERIES):
        results = [
            {"id": index * RESULTS_PER_QUERY + n, "title": f"document {index}-{n}"}
            for n in range(RESULTS_PER_QUERY)
        ]
        cache.put(f"query number {index}", results)

    held = retained()
    print(f"cache holds {cache.stats()['entries']} entries")
    print(held)


if __name__ == "__main__":
    main()
