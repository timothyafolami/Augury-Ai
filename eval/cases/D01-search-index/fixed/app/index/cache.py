"""Query-result cache in front of the index.

The index is expensive to consult, so results are memoised. The table is
bounded and evicts least-recently-used entries: the query space is whatever
users type, which is unbounded, and the process is long-lived.
"""

from __future__ import annotations

from collections import OrderedDict

# Chosen against the working set, not against the query space. A cache that
# must hold every distinct query is not a cache, it is a leak with a hit rate.
MAX_ENTRIES = 128

_entries: OrderedDict[str, list[dict[str, object]]] = OrderedDict()
_hits = 0
_misses = 0


def get(query: str) -> list[dict[str, object]] | None:
    global _hits, _misses
    hit = _entries.get(query)
    if hit is None:
        _misses += 1
        return None
    _entries.move_to_end(query)
    _hits += 1
    return hit


def put(query: str, results: list[dict[str, object]]) -> None:
    """Memoise a result set under its query, evicting the coldest if full."""
    _entries[query] = results
    _entries.move_to_end(query)
    while len(_entries) > MAX_ENTRIES:
        _entries.popitem(last=False)


def stats() -> dict[str, int]:
    return {"entries": len(_entries), "hits": _hits, "misses": _misses}


def clear() -> None:
    global _hits, _misses
    _entries.clear()
    _hits = 0
    _misses = 0
