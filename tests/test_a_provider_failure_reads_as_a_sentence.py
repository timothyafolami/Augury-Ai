"""A run that dies on the provider must say so in a line, not a stack trace.

The first DeepSeek run ended with sixty lines of Rich-rendered traceback
through httpx, openai and pydantic. Everything a reader needed -- which
provider, which model, what it said -- was on the last line, under a wall of
frames from libraries they did not call.
"""

from __future__ import annotations

import pytest

from augury.cli.main import _provider_failure


def test_the_provider_and_model_are_named() -> None:
    said = _provider_failure(RuntimeError("boom"), provider="deepseek", model="deepseek-v4-flash")
    assert "deepseek" in said
    assert "deepseek-v4-flash" in said


def test_what_the_provider_said_survives() -> None:
    said = _provider_failure(
        RuntimeError("Error code: 400 - response_format type is unavailable now"),
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    assert "response_format type is unavailable now" in said


def test_an_authentication_failure_names_the_key_to_set() -> None:
    """The commonest first-run failure, and the fix is one environment variable."""
    said = _provider_failure(
        RuntimeError("Error code: 401 - Authentication Fails"),
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    assert "DEEPSEEK_API_KEY" in said


def test_a_rate_limit_says_so_rather_than_reading_as_a_bug() -> None:
    said = _provider_failure(
        RuntimeError("Error code: 429 - Too Many Requests"),
        provider="groq",
        model="openai/gpt-oss-120b",
    )
    assert "rate limit" in said.lower()


def test_a_very_long_provider_message_is_cut_rather_than_printed_whole() -> None:
    said = _provider_failure(RuntimeError("x" * 5000), provider="groq", model="openai/gpt-oss-120b")
    assert len(said) < 1000


@pytest.mark.parametrize("provider", ["groq", "openai", "anthropic", "deepseek"])
def test_every_provider_has_a_key_to_name(provider: str) -> None:
    said = _provider_failure(RuntimeError("Error code: 401 - nope"), provider=provider, model="m")
    assert "_API_KEY" in said


def test_every_command_that_calls_a_model_catches_the_failure() -> None:
    """A guard that exists and is wired to nothing is this project's oldest bug.

    Reads the source rather than the behaviour, because the alternative is a
    live provider call per command.
    """
    import ast
    from pathlib import Path

    source = Path("src/augury/cli/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    guarded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        called = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        if "_provider_failure" in called:
            guarded += 1

    assert guarded >= 3, f"only {guarded} model-calling commands guard the provider"


def test_a_failure_that_is_not_about_the_key_does_not_blame_the_key() -> None:
    """It printed "set DEEPSEEK_API_KEY in .env" for a working key.

    Advice that names the wrong cause is worse than no advice: it sends the
    reader to check the one thing that was already right.
    """
    said = _provider_failure(
        RuntimeError("returned an empty response"),
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    assert "DEEPSEEK_API_KEY" not in said


def test_an_output_limit_is_named_as_one_with_the_setting_to_raise() -> None:
    said = _provider_failure(
        RuntimeError("hit the output limit before finishing"),
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    assert "AUGURY_MAX_TOKENS" in said
