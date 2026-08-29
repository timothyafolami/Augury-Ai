"""A cut-off answer is a length problem told as a format problem.

The first DeepSeek run failed three times on one module with:

    ValidationError: Invalid JSON: EOF while parsing a string at line 26

Each retry was told "return only the JSON instance, not the schema" -- advice
about shape, to a model whose shape was already right and whose answer simply
did not fit. So all three attempts produced the same truncation and the run
died on a module the model understood perfectly well.
"""

from __future__ import annotations

import pytest

from augury.core.adapters.provider import correction_for, ran_out_of_room
from tests.test_provider_adapter import Finding as _Finding


def test_a_json_document_that_ends_mid_string_is_a_length_failure() -> None:
    assert ran_out_of_room("Invalid JSON: EOF while parsing a string at line 26 column 129")


def test_an_unexpected_end_of_input_is_too() -> None:
    assert ran_out_of_room("Invalid JSON: EOF while parsing a value at line 3 column 1")


def test_a_wrong_field_is_not_a_length_failure() -> None:
    """This one really is about shape and must keep the shape correction."""
    assert not ran_out_of_room("1 validation error: findings.0.severity Input should be 'high'")


def test_a_cut_off_answer_is_asked_to_be_shorter_not_to_be_reshaped() -> None:
    said = correction_for("Invalid JSON: EOF while parsing a string at line 26")
    assert "fewer" in said or "shorter" in said


def test_a_malformed_answer_still_gets_the_shape_correction() -> None:
    said = correction_for("Input should be 'high', 'medium' or 'low'")
    assert "$defs" in said


def test_every_correction_quotes_what_went_wrong() -> None:
    for error in ("Invalid JSON: EOF while parsing", "Input should be 'high'"):
        assert error in correction_for(error)


async def test_an_answer_stopped_by_the_token_limit_is_named_as_one() -> None:
    """The provider says `finish_reason="length"`; we were reading the entrails.

    A reasoning model spends the output budget thinking before it answers, so
    a run that overflows comes back with empty content and a stop reason that
    explains exactly why. Guessing from the parse error instead produced
    "returned an empty response, which its provider documents as an occasional
    fault" -- for a fault that was neither occasional nor the provider's.
    """
    from tests.test_provider_adapter import adapter

    model = adapter("", provider="deepseek", finish_reason="length")

    with pytest.raises(Exception) as caught:
        await model.structured(prompt="review this", schema=_Finding)

    assert ran_out_of_room(str(caught.value)), str(caught.value)


async def test_a_complete_short_answer_is_not_mistaken_for_a_truncated_one() -> None:
    from tests.test_provider_adapter import adapter

    model = adapter('{"claim": "c", "confidence": 0.1}', provider="deepseek")

    assert await model.structured(prompt="review this", schema=_Finding) is not None


async def test_a_length_failure_is_retried_with_more_room_not_only_more_advice() -> None:
    """Telling a reasoning model to be brief does not give it space to answer.

    DeepSeek allows 384K output tokens and the configured ceiling was 16K, of
    which the chain of thought spent most before the answer began. Asking for
    fewer findings helps; raising the ceiling for the retry is what makes the
    difference between an answer and a third identical truncation.
    """
    from tests.test_provider_adapter import adapter

    model = adapter("", provider="deepseek", finish_reason="length", max_tokens=1000)

    with pytest.raises(ValueError):
        await model.structured(prompt="review this", schema=_Finding)

    asked = [call.get("extra_create_args", {}).get("max_tokens") for call in model._client.every]  # type: ignore[attr-defined]
    assert asked[1] is not None and asked[1] > 1000, f"retry asked for {asked}"


async def test_the_ceiling_does_not_grow_without_bound() -> None:
    from augury.core.adapters.provider import MOST_TOKENS
    from tests.test_provider_adapter import adapter

    model = adapter("", provider="deepseek", finish_reason="length", max_tokens=MOST_TOKENS)

    with pytest.raises(ValueError):
        await model.structured(prompt="review this", schema=_Finding)

    asked = [call.get("extra_create_args", {}).get("max_tokens") for call in model._client.every]  # type: ignore[attr-defined]
    assert all(value is None or value <= MOST_TOKENS for value in asked)


async def test_a_working_call_does_not_ask_for_a_raised_ceiling() -> None:
    """Only a length failure buys more room; everything else keeps the budget."""
    from tests.test_provider_adapter import adapter

    model = adapter('{"claim": "c", "confidence": 0.1}', provider="deepseek", max_tokens=1000)

    await model.structured(prompt="review this", schema=_Finding)

    sent = model._client.last_kwargs  # type: ignore[attr-defined]
    assert "max_tokens" not in sent.get("extra_create_args", {})
