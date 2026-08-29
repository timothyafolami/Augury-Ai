"""Query-result cache in front of the index.

The index is expensive to consult, so results are memoised. Every distinct
query string becomes an entry, and entries are never removed: the service is
long-lived and the query space is whatever users type.
"""

from __future__ import annotations

_entries: dict[str, list[dict[str, object]]] = {}
_hits = 0
_misses = 0


def get(query: str) -> list[dict[str, object]] | None:
    global _hits, _misses
    hit = _entries.get(query)
    if hit is None:
        _misses += 1
        return None
    _hits += 1
    return hit


def put(query: str, results: list[dict[str, object]]) -> None:
    """Memoise a result set under its query."""
    _entries[query] = results


def stats() -> dict[str, int]:
    return {"entries": len(_entries), "hits": _hits, "misses": _misses}


def clear() -> None:
    global _hits, _misses
    _entries.clear()
    _hits = 0
    _misses = 0
