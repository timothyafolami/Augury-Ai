"""Document storage over SQLite, one row per indexed document."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent / "documents.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, title TEXT, body TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS terms (doc_id INTEGER, term TEXT)")
    conn.commit()


def insert(conn: sqlite3.Connection, doc_id: int, title: str, body: str) -> None:
    conn.execute("INSERT INTO documents (id, title, body) VALUES (?, ?, ?)", (doc_id, title, body))
    conn.commit()


def by_id(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
