"""Triage is a routing decision, and it does not need the expensive model.

Every file gets one triage call before any specialist reads it, and that call
answers a narrow question: which concerns does this file touch. It is the
highest-volume call in the pipeline and the least demanding, and it was being
made by the same model that does the reasoning.

So a review of 476 modules paid the reasoning model to decide, 476 times,
whether a file mentions a database. A smaller model answers that as well and
costs a fraction, and the saving buys specialist calls on files the budget
would otherwise have stopped before.

`AUGURY_TRIAGE_MODEL` names it. Unset, triage uses the reviewing model, which
is what every recording so far was made against.

The cassette key includes the model id, so this is not a change that can be
made quietly: a run with a triage model set asks different recordings than one
without, and the two cannot be confused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.settings import load_settings


@pytest.fixture(autouse=True)
def _a_usable_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURY_PROVIDER", "groq")
    monkeypatch.setenv("AUGURY_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")
    monkeypatch.delenv("AUGURY_TRIAGE_MODEL", raising=False)


def test_without_the_variable_triage_uses_the_reviewing_model() -> None:
    """Which is what every recording committed to this repository was made
    against, so the default cannot change under them."""
    settings = load_settings()

    assert settings.triage_spec == settings.spec


def test_the_variable_gives_triage_its_own_model() -> None:
    import os

    os.environ["AUGURY_TRIAGE_MODEL"] = "openai/gpt-oss-20b"
    try:
        settings = load_settings()
    finally:
        del os.environ["AUGURY_TRIAGE_MODEL"]

    assert settings.triage_spec.model == "openai/gpt-oss-20b"
    assert settings.spec.model == "openai/gpt-oss-120b"


def test_the_triage_model_keeps_the_provider_and_the_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the model differs. A triage model on a second provider would need
    a second key, and a key nobody knew they had to set fails halfway through
    a review rather than before it starts."""
    monkeypatch.setenv("AUGURY_TRIAGE_MODEL", "openai/gpt-oss-20b")

    settings = load_settings()

    assert settings.triage_spec.provider == settings.spec.provider
    assert settings.triage_spec.max_tokens == settings.spec.max_tokens
    assert settings.triage_spec.temperature == settings.spec.temperature


def test_an_unpriced_triage_model_is_refused_before_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same check the reviewing model gets. A model with no published
    price makes every cost this tool reports a guess, and it is better to
    refuse than to report a number nobody can check."""
    from augury.core.settings import SettingsError

    monkeypatch.setenv("AUGURY_TRIAGE_MODEL", "a-model-nobody-has-priced")

    with pytest.raises(SettingsError):
        load_settings()


def test_the_reviewer_gives_triage_the_model_it_was_handed() -> None:
    """Settings alone change nothing. The routing model has to reach Triage,
    and the wiring is what a second spec exists for."""
    from augury.agents.augury import AuguryReviewer
    from tests.test_augury_arm import RoutingModel

    reviewing = RoutingModel()
    routing = RoutingModel()

    reviewer = AuguryReviewer(reviewing, triage_model=routing)

    assert reviewer._triage._model is routing


def test_triage_falls_back_to_the_reviewing_model() -> None:
    """One model stays the ordinary case, and the caller says nothing extra."""
    from augury.agents.augury import AuguryReviewer
    from tests.test_augury_arm import RoutingModel

    reviewing = RoutingModel()

    reviewer = AuguryReviewer(reviewing)

    assert reviewer._triage._model is reviewing


def test_model_from_can_build_the_routing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one place that decides live-versus-recorded has to build both, or
    the second model reaches past the guard that exists to stop a caller
    quietly spending money."""
    from augury.core.adapters.provider import triage_model_from

    monkeypatch.setenv("AUGURY_TRIAGE_MODEL", "openai/gpt-oss-20b")

    built = triage_model_from(load_settings())

    assert "gpt-oss-20b" in built.model_id


def test_the_routing_model_replays_from_cassettes_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Otherwise a keyless replay would reach for a provider to do triage."""
    from augury.core.adapters.cassette import CassetteModel
    from augury.core.adapters.provider import triage_model_from

    monkeypatch.setenv("AUGURY_TRIAGE_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("AUGURY_CASSETTES", str(tmp_path))

    assert isinstance(triage_model_from(load_settings()), CassetteModel)


def test_the_report_counts_what_the_routing_model_spent(tmp_path: Path) -> None:
    """Otherwise splitting the work hides half the bill.

    Every cost in the reviewer read `self._model.usage`, which is the
    reviewing model alone. Give triage its own model and its calls become
    free as far as the report is concerned -- so a change made to save money
    would have been reported as saving more than it did, which is the one
    kind of wrong number this tool cannot afford.
    """
    import asyncio

    from augury.agents.augury import AuguryReviewer
    from augury.core.cartography.mapper import Cartographer
    from tests.test_augury_arm import RoutingModel

    # Enough concerns that routing has something to narrow. Triage is skipped
    # when only one specialist qualifies, and a file that needs no routing
    # never calls the routing model.
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "db.py").write_text(
        "import sqlalchemy\n"
        "import httpx\n"
        "import hashlib\n"
        "import asyncio\n"
        "\n"
        "\n"
        "async def fetch(user):\n"
        "    async with httpx.AsyncClient() as client:\n"
        "        await client.get('http://api/' + user)\n"
        "    return hashlib.md5(user.encode()).hexdigest()\n",
        encoding="utf-8",
    )

    reviewing = RoutingModel(DraftReport={"findings": []}, DraftSynthesis={"observations": []})
    routing = RoutingModel(TriageDecision={"specialists": ["data"], "reasoning": "an ORM"})

    report = asyncio.run(
        AuguryReviewer(reviewing, triage_model=routing).review(
            Cartographer(tmp_path).map(), tmp_path
        )
    )

    assert routing.usage.usd > 0, "the routing model was never called"
    assert report.usd >= routing.usage.usd, (
        "the report left the routing model's spend out of the total"
    )
