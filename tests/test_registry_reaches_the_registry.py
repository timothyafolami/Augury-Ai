"""Asking PyPI about 34 packages one at a time loses nine of them.

Each lookup takes about a second on its own and the timeout is four, so a
batch run back to back queues behind itself until the tail times out. The
survey reported "25 of 34 checked" -- the nine were real packages that the
registry knows perfectly well.

Two fixes, both tested here without touching the network: ask concurrently,
and try a failed name once more before giving up on it.
"""

from __future__ import annotations

import json

from augury.core.reference.registry import Registry

_BODY = json.dumps({"info": {"name": "redis", "version": "7.0.0", "summary": "x"}, "releases": {}})


def test_a_lookup_that_fails_once_is_tried_again() -> None:
    """A single transient failure must not become a permanent unknown."""
    tries: list[str] = []

    def flaky(url: str) -> str | None:
        tries.append(url)
        return None if len(tries) == 1 else _BODY

    facts = Registry(fetch=flaky).facts_for("redis")
    assert facts is not None
    assert len(tries) == 2


def test_a_name_that_always_fails_is_given_up_on_rather_than_retried_forever() -> None:
    tries: list[str] = []

    def dead(url: str) -> str | None:
        tries.append(url)
        return None

    registry = Registry(fetch=dead)
    assert registry.facts_for("redis") is None
    assert len(tries) == 2, "one retry, not an unbounded loop"


def test_asking_for_many_answers_for_every_name() -> None:
    registry = Registry(fetch=lambda url: _BODY)
    answers = registry.facts_for_many(("redis", "pandas", "celery"))
    assert set(answers) == {"redis", "pandas", "celery"}


def test_asking_for_many_does_not_ask_twice_for_one_name() -> None:
    asked: list[str] = []

    def counting(url: str) -> str | None:
        asked.append(url)
        return _BODY

    registry = Registry(fetch=counting)
    registry.facts_for_many(("redis", "redis", "pandas"))
    assert len(asked) == 2


def test_an_answer_is_remembered_rather_than_asked_for_again() -> None:
    asked: list[str] = []

    def counting(url: str) -> str | None:
        asked.append(url)
        return _BODY

    registry = Registry(fetch=counting)
    registry.facts_for_many(("redis",))
    registry.facts_for("redis")
    assert len(asked) == 1


def test_a_truncated_response_is_a_missing_package_not_a_crash() -> None:
    """`http.client.IncompleteRead` is neither URLError, OSError nor ValueError.

    It escaped the "every failure is None" contract, propagated out of the
    thread pool mid-batch, and aborted the command before the review began --
    with a raw urllib traceback, because the dependency pass runs before the
    guard that turns a provider failure into a sentence.
    """
    import http.client

    def truncated(url: str) -> str | None:
        raise http.client.IncompleteRead(b'{"info":')

    assert Registry(fetch=truncated).facts_for("redis") is None


def test_a_truncated_response_lands_in_the_audit_rather_than_the_traceback() -> None:
    """The whole point of the Audit type: unreachable is reported, not raised."""
    import http.client

    from augury.core.reference.staleness import dependency_audit

    def truncated(url: str) -> str | None:
        raise http.client.IncompleteRead(b"")

    audit = dependency_audit({"redis": "4.0.0"}, Registry(fetch=truncated))

    assert audit.unreachable == ("redis",)


def test_a_batch_survives_one_package_that_raises() -> None:
    """One bad response must not take the other seven lookups with it."""
    import http.client

    def flaky(url: str) -> str | None:
        if "redis" in url:
            raise http.client.BadStatusLine("nonsense")
        return _BODY

    answers = Registry(fetch=flaky).facts_for_many(("redis", "pandas", "celery"))

    assert answers["redis"] is None
    assert answers["pandas"] is not None
