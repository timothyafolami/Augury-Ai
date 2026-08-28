"""A key in .env should be enough to run.

Requiring `export` before every command is a papercut that turns into "it does
not work on my machine" for anyone reproducing a run.
"""

from pathlib import Path

import pytest

from augury.core.settings import load_settings


def test_reads_a_key_from_a_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk-from-file\n")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    assert load_settings().api_key == "gsk-from-file"


def test_a_real_environment_variable_wins_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI sets real variables. A stale .env must not override them."""
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk-from-file\n")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-from-environment")
    monkeypatch.chdir(tmp_path)

    assert load_settings().api_key == "gsk-from-environment"


def test_the_example_file_documents_every_variable_the_code_reads() -> None:
    """A variable that exists in code but not in .env.example is a variable
    nobody will discover."""
    example = (Path(__file__).parent.parent / ".env.example").read_text()

    for variable in (
        "AUGURY_PROVIDER",
        "AUGURY_MODEL",
        "AUGURY_TEMPERATURE",
        "AUGURY_REPLAY_ONLY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        assert variable in example, f"{variable} is undocumented in .env.example"
