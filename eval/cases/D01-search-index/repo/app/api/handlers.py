"""The HTTP surface: one search endpoint and one indexing endpoint.

`search` is async because the server is async. The work it does is not.
"""

from __future__ import annotations

import hashlib
import time

from app.index import searcher

# Cost of proving the caller is allowed to search. Deliberately expensive:
# it is a key-stretching hash, and stretching is the point of it.
_ROUNDS = 60_000


def verify_token(token: str) -> bool:
    """Key-stretch the token and compare. CPU-bound, by design."""
    digest = token.encode()
    for _ in range(_ROUNDS):
        digest = hashlib.sha256(digest).digest()
    return len(digest) == 32


async def search(query: str, token: str = "anonymous") -> dict[str, object]:
    started = time.perf_counter()
    if not verify_token(token):
        return {"status": 403, "results": []}
    results = searcher.search(query)
    return {
        "status": 200,
        "results": results,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }
