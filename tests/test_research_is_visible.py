"""Two of this reviewer's inputs come off the internet, and neither said so.

The registry is asked what version of a package is current, because a model
answers that from its training cutoff and confidently. Search is asked where a
changelog is, because nothing else knows. Both are real network calls that
shape what the review claims, and both happened silently: a reader watching a
run saw a gap where the reviewer was doing the one kind of work it cannot do
from the code alone.

An unobserved input is exactly the thing this project reports on elsewhere.
"""

from __future__ import annotations

import json

from augury.core.reference.changelog import changelog_notes
from augury.core.reference.registry import Registry

_BODY = json.dumps({"info": {"name": "redis", "version": "7.0.0", "summary": "x"}, "releases": {}})


def test_asking_the_registry_is_announced_before_the_answer_arrives() -> None:
    """Announced before, or a slow lookup is a silence with no explanation."""
    seen: list[dict[str, object]] = []

    Registry(fetch=lambda url: _BODY, watching=seen.append).facts_for("redis")

    assert [step["state"] for step in seen] == ["asked", "answered"]
    assert seen[0]["subject"] == "redis"


def test_the_registry_names_where_it_asked() -> None:
    seen: list[dict[str, object]] = []

    Registry(fetch=lambda url: _BODY, watching=seen.append).facts_for("redis")

    assert seen[0]["source"] == "pypi.org"


def test_the_answer_carries_what_was_learned() -> None:
    seen: list[dict[str, object]] = []

    Registry(fetch=lambda url: _BODY, watching=seen.append).facts_for("redis")

    assert seen[1]["found"] is True
    assert seen[1]["detail"] == "7.0.0"


def test_a_package_the_registry_cannot_answer_for_says_so() -> None:
    """Silence here reads as a package with nothing wrong, which is a lie."""
    seen: list[dict[str, object]] = []

    Registry(fetch=lambda url: None, watching=seen.append).facts_for("internal-thing")

    assert seen[-1]["found"] is False


def test_a_cached_answer_is_not_announced_twice() -> None:
    """The second call reaches no network, so announcing it invents a lookup."""
    seen: list[dict[str, object]] = []
    registry = Registry(fetch=lambda url: _BODY, watching=seen.append)

    registry.facts_for("redis")
    registry.facts_for("redis")

    assert sum(1 for step in seen if step["state"] == "asked") == 1


def test_searching_for_a_changelog_is_announced() -> None:
    seen: list[dict[str, object]] = []

    changelog_notes(
        "redis",
        "4.0.0",
        "7.0.0",
        search=lambda query, limit: [{"title": "Redis 7", "href": "https://example.com/c"}],
        watching=seen.append,
    )

    assert [step["state"] for step in seen] == ["asked", "answered"]
    assert "redis" in str(seen[0]["subject"])


def test_the_search_names_the_engine_rather_than_calling_itself_research() -> None:
    """Which engine answered is the part a reader needs to weigh it."""
    seen: list[dict[str, object]] = []

    changelog_notes(
        "redis",
        "4.0.0",
        "7.0.0",
        search=lambda query, limit: [],
        watching=seen.append,
    )

    assert seen[0]["source"] == "duckduckgo"


def test_a_search_that_finds_nothing_is_announced_as_nothing() -> None:
    seen: list[dict[str, object]] = []

    changelog_notes("x", "1", "2", search=lambda query, limit: [], watching=seen.append)

    assert seen[-1]["found"] is False


def test_a_search_that_fails_is_announced_rather_than_swallowed() -> None:
    """Search is the first thing to go on a train, and the run continues.

    It continuing quietly is the problem: the report then omits a section for
    a reason nobody watching could name.
    """
    seen: list[dict[str, object]] = []

    def broken(query: str, limit: int) -> list[dict[str, str]]:
        raise RuntimeError("no network")

    changelog_notes("x", "1", "2", search=broken, watching=seen.append)

    assert seen[-1]["state"] == "answered"
    assert seen[-1]["found"] is False
