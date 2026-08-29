"""DeepSeek rejects the schema-shaped response_format the others accept.

    BadRequestError: 400 - This response_format type is unavailable now

The first real DeepSeek run died on the first model call. Its API is
OpenAI-compatible in every other respect, so the fix is not a second client:
it is asking for a JSON object rather than for a named schema, and putting
the schema in the prompt where a model without strict decoding can still see
it. Validation is unchanged -- the answer is still parsed into the model, and
still raised if it does not fit.
"""

from __future__ import annotations

from pydantic import BaseModel

from augury.core.adapters.provider import (
    came_back_empty,
    correction_for,
    schema_in_prompt,
    wants_named_schema,
)


class _Answer(BaseModel):
    verdict: str


def test_deepseek_is_not_asked_for_a_named_schema() -> None:
    assert not wants_named_schema("deepseek")


def test_the_providers_with_strict_decoding_still_get_one() -> None:
    assert wants_named_schema("openai")
    assert wants_named_schema("groq")
    assert wants_named_schema("anthropic")


def test_an_unknown_provider_is_not_assumed_to_support_it() -> None:
    """A 400 on the first call is a worse default than a schema in the prompt."""
    assert not wants_named_schema("some-new-gateway")


def test_the_schema_is_put_where_a_model_without_strict_decoding_can_read_it() -> None:
    asked = schema_in_prompt("Review this module.", _Answer)
    assert "Review this module." in asked
    assert "verdict" in asked


def test_the_original_prompt_is_not_lost_behind_the_schema() -> None:
    asked = schema_in_prompt("Review this module.", _Answer)
    assert asked.index("Review this module.") < asked.index("verdict")


def test_the_prompt_contains_the_literal_word_json() -> None:
    """DeepSeek's JSON mode requires it: "Include the word 'json' in the ...
    system or user prompt, and provide an example of the desired JSON format".

    A prompt that says "JSON" only inside a schema dump is not something to
    rely on when the documented requirement is this specific.
    """
    assert "json" in schema_in_prompt("Review this.", _Answer)


def test_the_prompt_carries_an_example_instance_not_only_a_schema() -> None:
    """The other half of the same documented requirement.

    A schema describes the shape; the docs ask for an example of it, and a
    model without strict decoding follows an example more reliably than a
    `$defs` block.
    """
    asked = schema_in_prompt("Review this.", _Answer)
    assert '"verdict":' in asked


def test_an_empty_answer_is_reported_as_empty_rather_than_as_bad_json() -> None:
    """DeepSeek documents this: "the API may occasionally return empty content".

    Parsed as JSON it becomes "expecting value at line 1", which reads like a
    malformed answer and earns the wrong retry advice.
    """
    assert came_back_empty("")
    assert came_back_empty("   \n ")
    assert not came_back_empty('{"verdict": "ok"}')


def test_an_empty_answer_is_told_to_say_nothing_explicitly() -> None:
    """The commonest empty response is a specialist with nothing to report.

    Instrumenting a real run showed the pattern: 8 completion tokens, 20
    characters of reasoning, no content. The model had found nothing and
    emitted nothing, where the schema wanted an empty list. Telling it to
    "return only the JSON instance, not the schema" answers a question it did
    not get wrong.
    """
    said = correction_for("returned an empty response")
    assert "empty" in said.lower()
    assert "[]" in said or "empty list" in said


def test_an_empty_answer_is_not_mistaken_for_a_truncated_one() -> None:
    """Opposite advice: one should be shorter, the other should exist at all."""
    said = correction_for("returned an empty response")
    assert "fewer findings" not in said
