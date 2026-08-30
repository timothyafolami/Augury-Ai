"""Model choice is configuration, not code.

A judge reproducing a run, and we ourselves swapping 20b for 120b to see what
capability the result actually depends on, both need this to be an environment
variable rather than an edit.
"""

from pathlib import Path

import pytest

from augury.core.settings import SettingsError, load_settings


@pytest.fixture(autouse=True)
def _no_developer_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point .env somewhere empty for every test in this file.

    Without this these tests read whichever .env the developer happens to
    have, so "what does it default to" is answered by a gitignored file and
    the suite passes or fails depending on who runs it. That is exactly how
    this fixture came to be written.
    """
    monkeypatch.setattr("augury.core.settings._dotenv_path", lambda: tmp_path / ".env")


def test_defaults_to_gpt_oss_120b_on_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured against the alternative rather than assumed.

    DeepSeek v4-flash has the lower published price per token and cost
    eighteen times as much per module, because a reasoning model's chain of
    thought is billed as output. The committed cassettes are Groq recordings
    too, so this is also the model `make eval-replay` reproduces.
    """
    monkeypatch.delenv("AUGURY_PROVIDER", raising=False)
    monkeypatch.delenv("AUGURY_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    settings = load_settings()

    assert settings.spec.provider == "groq"
    assert settings.spec.model == "openai/gpt-oss-120b"


def test_a_dotenv_supplies_what_the_environment_does_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The path a user takes: fill in .env, run the command, no exports."""
    monkeypatch.delenv("AUGURY_PROVIDER", raising=False)
    monkeypatch.delenv("AUGURY_MODEL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    written = tmp_path / ".env"
    written.write_text(
        "AUGURY_PROVIDER=groq\nAUGURY_MODEL=openai/gpt-oss-120b\nGROQ_API_KEY=gsk-x\n"
    )
    monkeypatch.setattr("augury.core.settings._dotenv_path", lambda: written)

    settings = load_settings()

    assert settings.spec.provider == "groq"
    assert settings.spec.model == "openai/gpt-oss-120b"


def test_the_smaller_model_is_selected_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the same evaluation on 20b and 120b is how we find out whether
    a result depends on model capability or on the architecture around it."""
    monkeypatch.setenv("AUGURY_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    assert load_settings().spec.model == "openai/gpt-oss-20b"


def test_reads_the_api_key_for_the_selected_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.setenv("AUGURY_PROVIDER", "anthropic")
    monkeypatch.setenv("AUGURY_MODEL", "claude-sonnet-4-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    assert load_settings().api_key == "sk-ant-test"


def test_a_missing_key_names_the_variable_to_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("AUGURY_PROVIDER", raising=False)

    # Names the default provider's variable, which is Groq's.
    with pytest.raises(SettingsError, match="GROQ_API_KEY"):
        load_settings()


def test_an_unknown_provider_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURY_PROVIDER", "nonesuch")

    with pytest.raises(SettingsError, match="nonesuch"):
        load_settings()


def test_an_unpriced_model_is_refused_before_a_run_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Better here than at the end of a review that reports itself as free."""
    monkeypatch.setenv("AUGURY_MODEL", "some-model-we-have-not-priced")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    with pytest.raises(SettingsError, match="pricing"):
        load_settings()


def test_replay_only_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """`make eval-replay` is the path a judge takes. It must not require a key."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")

    settings = load_settings()

    assert settings.replay_only is True
    assert settings.api_key == ""


def test_a_generous_output_budget_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """gpt-oss reasons before it answers. The provider default cut it off
    mid-thought, so the request failed with an empty generation rather than a
    truncated one, which reads like a schema problem and is not."""
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.delenv("AUGURY_MAX_TOKENS", raising=False)

    assert load_settings().spec.max_tokens >= 8000


def test_the_output_budget_can_be_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("AUGURY_MAX_TOKENS", "32000")

    assert load_settings().spec.max_tokens == 32000
