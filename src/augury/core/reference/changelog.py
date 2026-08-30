"""What changed between two versions, which the registry does not know.

PyPI gives numbers: redis is pinned at 5.2.0 and ships 8.1.0. It does not say
what three majors of redis-py changed, and that is the part a reader needs
before touching the client their broker runs on.

Search answers it, and search is the least trustworthy input in this project. A
version number is a fact; a snippet is somebody's prose about a fact. So every
note here is **quoted, attributed to its URL, and never turned into a finding**.
The reviewer says "worth reading before upgrading"; it does not say "this
breaks you".

Optional throughout. A failure returns nothing, because a review has to work on
a train and search is the first thing to go.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

RESULTS = 4

# Hosts that publish releases rather than write about them. A project's own
# release page is evidence; a listicle containing the same words is not.
AUTHORITATIVE = (
    "github.com",
    "gitlab.com",
    "readthedocs.io",
    "docs.python.org",
    "pypi.org",
    "changelog.md",
)


@dataclass(frozen=True)
class Note:
    """One search result, kept as a quotation with its source."""

    title: str
    url: str
    snippet: str

    def as_reading_note(self) -> str:
        """How this is allowed to appear in a report.

        Never as a claim. The reviewer has not read the changelog; it has found
        where the changelog is.
        """
        return f"Worth reading before upgrading: {self.title} — {self.url}"


Searcher = Callable[[str, int], list[dict[str, str]]]


def _ddgs(query: str, limit: int) -> list[dict[str, str]]:
    """DuckDuckGo, which needs no key and no account."""
    from ddgs import DDGS

    with DDGS() as client:
        return [dict(row) for row in client.text(query, max_results=limit)]


def changelog_notes(
    package: str,
    pinned: str,
    latest: str,
    *,
    search: Searcher = _ddgs,
    watching: Callable[[dict[str, object]], None] | None = None,
) -> tuple[Note, ...]:
    """Where to read about the gap between two versions."""
    query = f"{package} changelog breaking changes {pinned} to {latest}"

    def say(state: str, **rest: object) -> None:
        if watching is not None:
            watching(
                {
                    "kind": "research",
                    "source": "duckduckgo",
                    "subject": query,
                    "state": state,
                    **rest,
                }
            )

    say("asked")
    try:
        results = search(query, RESULTS)
    except Exception as failed:
        # Search is the first thing to go on a train and the run continues.
        # It continuing quietly is the problem: the report then omits a
        # section for a reason nobody watching could name.
        say("answered", found=False, detail=f"search failed: {failed}")
        return ()

    notes = [
        Note(
            title=str(row.get("title") or "").strip(),
            url=str(row.get("href") or row.get("url") or "").strip(),
            snippet=str(row.get("body") or "").strip(),
        )
        for row in results
    ]
    notes = [note for note in notes if note.url.startswith("http")]
    # A project's own release page first, whatever the engine ranked -- but
    # only when it is that project's page. Searching redis-py returns
    # fakeredis's changelog on an authoritative host, and host authority alone
    # put a different project first.
    notes.sort(key=lambda note: (-_rank(note, package), note.url))
    say(
        "answered",
        found=bool(notes),
        detail=notes[0].url if notes else "nothing usable returned",
    )
    return tuple(notes)


def _rank(note: Note, package: str) -> int:
    """Authoritative and about this package beats either one alone.

    Matched on boundaries, not as a substring: `redis` appears inside
    `fakeredis`, and a substring match scored a different project's changelog
    exactly as highly as the right one.
    """
    haystack = f"{note.url} {note.title}".lower()
    stem = package.lower().replace("_", "-")
    names = {name for name in (stem, stem.removesuffix("-py")) if name}

    # A path segment that *is* the package. `django-redis` mentions redis on a
    # boundary and is a different project; `/redis-py/` is the project itself.
    segments = {part for part in note.url.lower().split("/") if part}
    owned = bool(names & segments)

    mentioned = any(
        re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", haystack) for name in names
    )
    return 2 * int(_authoritative(note.url)) + 3 * int(mentioned) + 5 * int(owned)


def _authoritative(url: str) -> bool:
    return any(host in url.lower() for host in AUTHORITATIVE)
