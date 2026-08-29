"""Turns a document into the terms the index stores against it."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")


def terms(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def normalise(query: str) -> str:
    """Queries differing only in spacing or case are the same query."""
    return " ".join(terms(query))
