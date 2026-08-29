"""How many database queries one search costs.

Counts every statement the connection executes while serving a single search
over a fixed corpus, by installing SQLite's own trace callback rather than by
instrumenting the application. An earlier experiment in this project counted
queries by looping over its own query and reported a number that had nothing
to do with the endpoint.

The corpus is fixed and the query matches a known number of documents, so the
count is arithmetic: one listing query, plus whatever the code does per result.

What would mean the experiment is broken rather than the prediction wrong: a
count of zero or one on the seeded repository, which would mean the search
never reached the database -- most likely because the cache answered it. The
cache is cleared before the run for exactly that reason.

The last line printed is the measurement, as queries.
"""

import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from app.index import cache, searcher  # noqa: E402
from app.store import documents  # noqa: E402

MATCHING_DOCUMENTS = 40


def main() -> None:
    conn = documents.connect()
    documents.create_schema(conn)
    conn.execute("DELETE FROM documents")
    for doc_id in range(MATCHING_DOCUMENTS):
        conn.execute(
            "INSERT INTO documents (id, title, body) VALUES (?, ?, ?)",
            (doc_id, f"report on widgets number {doc_id}", f"body of document {doc_id}"),
        )
    conn.commit()
    conn.close()
    cache.clear()

    print(f"one search over {MATCHING_DOCUMENTS} matching documents, cache cold")

    counted = {"n": 0}
    original = documents.connect

    def counting_connect() -> sqlite3.Connection:
        conn = original()
        conn.set_trace_callback(lambda statement: counted.__setitem__("n", counted["n"] + 1))
        return conn

    documents.connect = counting_connect  # type: ignore[assignment]
    try:
        searcher.search("widgets")
    finally:
        documents.connect = original  # type: ignore[assignment]

    print(counted["n"])


if __name__ == "__main__":
    main()
