"""The half PyPI cannot answer: what changed between two versions.

The registry gives numbers -- redis is pinned at 5.2.0 and ships 8.1.0. It does
not say what three majors of redis-py changed, and that is the part a reader
needs before upgrading the client their Celery broker runs on.

Search answers that, and search is the least trustworthy input in this project:
a snippet is somebody's prose, not a fact the way a version number is. So it is
quoted rather than asserted, always attributed to its URL, and never allowed to
become a finding on its own.

No test here touches the network. The searcher is injected.
"""

from __future__ import annotations

from augury.core.reference.changelog import Note, changelog_notes

RESULTS = [
    {
        "title": "redis-py 6.0.0 release notes",
        "href": "https://github.com/redis/redis-py/releases/tag/v6.0.0",
        "body": (
            "Drops Python 3.7. Connection pool defaults changed: max_connections now unbounded."
        ),
    },
    {
        "title": "Some blog about redis",
        "href": "https://example.com/redis-tips",
        "body": "Ten tips for redis performance you will not believe.",
    },
]


def _search(results: list[dict[str, str]] | None = None):  # type: ignore[no-untyped-def]
    served = RESULTS if results is None else results

    def search(query: str, limit: int) -> list[dict[str, str]]:
        return served[:limit]

    return search


def test_notes_are_returned_with_their_source() -> None:
    notes = changelog_notes("redis", "5.2.0", "8.1.0", search=_search())

    assert notes
    assert all(isinstance(note, Note) for note in notes)
    assert notes[0].url.startswith("https://")


def test_the_query_names_both_versions_and_the_package() -> None:
    asked: list[str] = []

    def search(query: str, limit: int) -> list[dict[str, str]]:
        asked.append(query)
        return []

    changelog_notes("redis", "5.2.0", "8.1.0", search=search)

    assert "redis" in asked[0]
    assert "5.2.0" in asked[0] and "8.1.0" in asked[0]


def test_a_result_from_the_project_itself_outranks_a_blog() -> None:
    """A release page is evidence; a listicle about the same words is not."""
    notes = changelog_notes("redis", "5.2.0", "8.1.0", search=_search())

    assert "github.com/redis/redis-py" in notes[0].url


def test_a_searcher_that_fails_returns_nothing_rather_than_raising() -> None:
    """Search is optional. A review must work offline and must not stop here."""

    def search(query: str, limit: int) -> list[dict[str, str]]:
        raise OSError("no network")

    assert changelog_notes("redis", "5.2.0", "8.1.0", search=search) == ()


def test_notes_are_never_presented_as_findings() -> None:
    """The one rule that matters: a snippet is somebody's prose.

    It is quoted, attributed, and offered as something to read -- never turned
    into a claim about this repository.
    """
    note = changelog_notes("redis", "5.2.0", "8.1.0", search=_search())[0]

    assert note.as_reading_note().startswith("Worth reading before upgrading")
    assert note.url in note.as_reading_note()


def test_a_result_about_a_different_package_ranks_below_one_about_this_one() -> None:
    """Searching redis-py returns fakeredis, on an authoritative host.

    Host authority alone put a different project's changelog first. A result
    has to be authoritative *and* about the package asked for.
    """
    results = [
        {
            "title": "Change log - fakeredis",
            "href": "https://fakeredis.readthedocs.io/en/latest/about/changelog/",
            "body": "fix: validate command option values",
        },
        {
            "title": "Releases · redis/redis-py",
            "href": "https://github.com/redis/redis-py/releases",
            "body": "the default protocol has been changed from RESP2 to RESP3",
        },
    ]

    notes = changelog_notes("redis-py", "5.2.0", "8.1.0", search=_search(results))

    assert "redis/redis-py" in notes[0].url
