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
        rows = conn.execute("SELECT id, title, body FROM documents").fetchall()
        wanted = set(tokenizer.terms(key))
        # One query, selecting the body the snippet needs. Fetching it per row
        # afterwards costs a query per result and returns the same answer.
        results = [
            {
                "id": row["id"],
                "title": row["title"],
                "snippet": str(row["body"])[:80],
            }
            for row in rows
            if wanted & set(tokenizer.terms(row["title"]))
        ]
    finally:
        conn.close()

    cache.put(key, results)
    return results[:limit]
