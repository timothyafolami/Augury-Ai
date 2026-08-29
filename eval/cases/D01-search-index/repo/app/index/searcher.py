"""Searching the index.

Consults the cache first, then the store. The scan itself is deliberately
simple: correctness here is not the subject.
"""

from __future__ import annotations

from app.index import cache, tokenizer
from app.store import documents


def search(query: str, limit: int = 10) -> list[dict[str, object]]:
    key = tokenizer.normalise(query)
    cached = cache.get(key)
    if cached is not None:
        return cached[:limit]

    conn = documents.connect()
    try:
        rows = conn.execute("SELECT id, title FROM documents").fetchall()
        wanted = set(tokenizer.terms(key))
        results = []
        for row in rows:
            if not wanted & set(tokenizer.terms(row["title"])):
                continue
            # The snippet comes from the body, which the listing query did not
            # select.
            full = documents.by_id(conn, row["id"])
            body = "" if full is None else str(full["body"])
            results.append({"id": row["id"], "title": row["title"], "snippet": body[:80]})
    finally:
        conn.close()

    cache.put(key, results)
    return results[:limit]
