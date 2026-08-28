"""Recorded model calls are what make the evaluation reproducible for free.

A judge with no API key must be able to replay every published number, a
replay must never quietly fall through to a live call, and the spend we report
must be the spend that happened.
"""

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from augury.core.adapters.base import ChatModel, Usage
from augury.core.adapters.cassette import CassetteCorrupt, CassetteMiss, CassetteModel


class Answer(BaseModel):
    verdict: str


class OtherAnswer(BaseModel):
    verdict: str


class AccumulatingModel:
    """A stand-in that accumulates usage the way a real provider SDK does.

    This detail is load-bearing. A double that resets its usage on every call
    hides double-counting in any wrapper that reads cumulative usage, which is
    exactly the mock-that-lies failure the wrapper is meant to be safe from.
    """

    def __init__(self, model_id: str = "stub-1") -> None:
        self._model_id = model_id
        self.calls = 0
        self._usage = Usage()

    @property
    def model_id(self) -> str:
        return self._model_id

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        self.calls += 1
        await asyncio.sleep(0)  # a real client yields; concurrency tests need this
        self._usage = self._usage + Usage(input_tokens=10, output_tokens=5, usd=0.02)
        return schema(verdict=f"answer to {prompt}")

    @property
    def usage(self) -> Usage:
        return self._usage


def test_cassette_model_satisfies_the_chat_model_protocol(tmp_path: Path) -> None:
    """The wrapper is handed to agents wherever a ChatModel is expected, so
    mypy must agree it is one. The annotation is the check."""
    model: ChatModel = CassetteModel(AccumulatingModel(), tmp_path)

    assert model.model_id == "stub-1"


# -- recording -------------------------------------------------------------


async def test_first_call_delegates_to_the_inner_model(tmp_path: Path) -> None:
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path)

    result = await model.structured(prompt="why is it slow", schema=Answer)

    assert inner.calls == 1
    assert result.verdict == "answer to why is it slow"


async def test_a_recording_is_written_to_disk(tmp_path: Path) -> None:
    """Cassettes are committed artefacts. An in-memory cache would pass every
    behavioural test here and ship a repo with no cassettes in it."""
    model = CassetteModel(AccumulatingModel(), tmp_path)

    await model.structured(prompt="why is it slow", schema=Answer)

    assert len(list(tmp_path.glob("*.json"))) == 1


async def test_identical_call_replays_without_touching_the_inner_model(tmp_path: Path) -> None:
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path)

    first = await model.structured(prompt="why is it slow", schema=Answer)
    second = await model.structured(prompt="why is it slow", schema=Answer)

    assert inner.calls == 1
    assert second == first


async def test_a_fresh_instance_replays_recordings_left_by_an_earlier_run(tmp_path: Path) -> None:
    """Cross-process replay is the whole point: the judge is not the process
    that recorded."""
    await CassetteModel(AccumulatingModel(), tmp_path).structured(prompt="q", schema=Answer)

    later = AccumulatingModel()
    result = await CassetteModel(later, tmp_path).structured(prompt="q", schema=Answer)

    assert later.calls == 0
    assert result.verdict == "answer to q"


# -- cache key -------------------------------------------------------------


async def test_a_different_prompt_records_a_separate_cassette(tmp_path: Path) -> None:
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path)

    await model.structured(prompt="why is it slow", schema=Answer)
    await model.structured(prompt="why is it wrong", schema=Answer)

    assert inner.calls == 2


async def test_two_providers_never_share_a_cassette(tmp_path: Path) -> None:
    """The cross-model robustness run compares two providers. If they collide
    on one cassette, that comparison is silently falsified."""
    anthropic = AccumulatingModel("claude")
    openai = AccumulatingModel("gpt")

    await CassetteModel(anthropic, tmp_path).structured(prompt="q", schema=Answer)
    await CassetteModel(openai, tmp_path).structured(prompt="q", schema=Answer)

    assert anthropic.calls == 1
    assert openai.calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 2


async def test_a_changed_response_schema_is_a_different_recording(tmp_path: Path) -> None:
    """Replaying an answer shaped for an older schema is worse than a miss."""
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path)

    await model.structured(prompt="q", schema=Answer)
    await model.structured(prompt="q", schema=OtherAnswer)

    assert inner.calls == 2


# -- spend accounting ------------------------------------------------------


async def test_reported_spend_matches_what_was_actually_spent(tmp_path: Path) -> None:
    """Reading a provider's cumulative usage and adding it every call sums
    prefix sums, inflating reported cost. The delta is what is owed."""
    model = CassetteModel(AccumulatingModel(), tmp_path)

    for i in range(4):
        await model.structured(prompt=f"q{i}", schema=Answer)

    assert model.usage == Usage(input_tokens=40, output_tokens=20, usd=0.08)


async def test_a_replayed_call_adds_no_spend(tmp_path: Path) -> None:
    model = CassetteModel(AccumulatingModel(), tmp_path)

    await model.structured(prompt="q", schema=Answer)
    await model.structured(prompt="q", schema=Answer)

    assert model.usage == Usage(input_tokens=10, output_tokens=5, usd=0.02)


def test_usage_totals_can_be_summed_across_a_mesh_of_agents() -> None:
    per_agent = [Usage(input_tokens=1, usd=0.01), Usage(input_tokens=2, usd=0.02)]

    assert sum(per_agent, Usage()) == Usage(input_tokens=3, usd=0.03)


# -- replay-only guarantees ------------------------------------------------


async def test_replay_only_serves_a_recording_when_one_exists(tmp_path: Path) -> None:
    """The success path of `make eval-replay`. Untested, this can be wholly
    broken for judges while the suite stays green."""
    await CassetteModel(AccumulatingModel(), tmp_path).structured(prompt="q", schema=Answer)

    judge_side = AccumulatingModel()
    result = await CassetteModel(judge_side, tmp_path, replay_only=True).structured(
        prompt="q", schema=Answer
    )

    assert judge_side.calls == 0
    assert result.verdict == "answer to q"


async def test_replay_only_refuses_to_reach_the_network(tmp_path: Path) -> None:
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path, replay_only=True)

    with pytest.raises(CassetteMiss, match="no recording"):
        await model.structured(prompt="never recorded", schema=Answer)

    assert inner.calls == 0


def test_replay_only_against_a_missing_directory_says_so(tmp_path: Path) -> None:
    """A mistyped path must not be reported as 'go spend money re-recording'."""
    with pytest.raises(CassetteMiss, match="does not exist"):
        CassetteModel(AccumulatingModel(), tmp_path / "typo", replay_only=True)


# -- robustness ------------------------------------------------------------


async def test_a_corrupt_cassette_names_the_file(tmp_path: Path) -> None:
    """A truncated cassette gets committed and reaches a judge. The error has
    to point at the file, not at the response schema."""
    model = CassetteModel(AccumulatingModel(), tmp_path, replay_only=True)
    await CassetteModel(AccumulatingModel(), tmp_path).structured(prompt="q", schema=Answer)
    next(tmp_path.glob("*.json")).write_text("{trunca", encoding="utf-8")

    with pytest.raises(CassetteCorrupt, match=r"\.json"):
        await model.structured(prompt="q", schema=Answer)


async def test_non_ascii_survives_a_record_and_replay_round_trip(tmp_path: Path) -> None:
    """Model output contains em-dashes and non-Latin text. Without an explicit
    encoding this decodes differently on a judge's machine."""
    model = CassetteModel(AccumulatingModel(), tmp_path)

    recorded = await model.structured(prompt="grüße — 你好", schema=Answer)
    replayed = await CassetteModel(AccumulatingModel(), tmp_path).structured(
        prompt="grüße — 你好", schema=Answer
    )

    assert replayed == recorded


async def test_concurrent_identical_calls_collapse_to_one_live_call(tmp_path: Path) -> None:
    """Agents in the mesh issue the same prompt concurrently. Check-then-act
    without a lock bills once per caller and races on the write."""
    inner = AccumulatingModel()
    model = CassetteModel(inner, tmp_path)

    await asyncio.gather(*(model.structured(prompt="q", schema=Answer) for _ in range(5)))

    assert inner.calls == 1
