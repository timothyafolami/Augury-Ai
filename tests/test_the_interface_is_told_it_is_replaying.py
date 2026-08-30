"""Replay mode is invisible, and invisible it looks like a broken review.

`make demo` runs with AUGURY_REPLAY_ONLY=1, which serves every model call from
a committed recording. Pointed at one of the recorded cases that is the whole
product for free. Pointed at anything else, every call misses, no specialist
answers, and the interface shows a review that read 68 of 476 modules, spent
$0.0000 and found nothing -- with no indication anywhere that it was never
going to find anything.

That is the worst failure available: it is indistinguishable from a model that
is not working, and the first thing someone does is doubt the product.

The server knows. It just never said. This asserts it says.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from augury.server.app import build


def test_replay_mode_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")

    answer = TestClient(build()).get("/api/mode")

    assert answer.status_code == 200
    assert answer.json()["replay"] is True


def test_live_mode_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUGURY_REPLAY_ONLY", raising=False)

    answer = TestClient(build()).get("/api/mode")

    assert answer.json()["replay"] is False


def test_replay_names_the_repositories_it_can_actually_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A warning with no remedy is a nuisance. The recorded cases are the
    remedy, and the server is the only thing that knows which they are."""
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")

    recorded = TestClient(build()).get("/api/mode").json()["recorded"]

    assert any("B01-orders-service" in path for path in recorded)
    assert any("E01-go-inventory" in path for path in recorded)
    assert any("F01-ts-checkout" in path for path in recorded)


def test_live_mode_offers_no_recordings(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is nothing to steer anyone towards when every repository works."""
    monkeypatch.delenv("AUGURY_REPLAY_ONLY", raising=False)

    assert TestClient(build()).get("/api/mode").json()["recorded"] == []


def test_the_first_recorded_case_is_the_one_worth_showing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The interface offers the first as its default, so the order is a choice.

    Alphabetical put A04 first, which is three files and is documented in its
    own manifest as deliberately easy -- "a repository where reading
    everything is free". Landing a first-time reviewer on the case designed
    not to discriminate is the worst available introduction.
    """
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")

    recorded = TestClient(build()).get("/api/mode").json()["recorded"]

    assert "A04" not in recorded[0]
    assert "B01-orders-service" in recorded[0]
