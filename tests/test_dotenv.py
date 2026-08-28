"""A key in .env should be enough to run.

Requiring `export` before every command is a papercut that turns into "it does
not work on my machine" for anyone reproducing a run.

The file is Augury's own, located by installation rather than by working
directory, because the working directory is frequently a repository under
review. Tests point AUGURY_ENV_FILE at a fixture rather than chdir-ing.
"""

from pathlib import Path

import pytest

from augury.core.settings import load_settings


def test_reads_a_key_from_a_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=gsk-from-file\n")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("AUGURY_ENV_FILE", str(env_file))

    assert load_settings().api_key == "gsk-from-file"


def test_a_real_environment_variable_wins_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI sets real variables. A stale .env must not override them."""
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=gsk-from-file\n")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-from-environment")
    monkeypatch.setenv("AUGURY_ENV_FILE", str(env_file))

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


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("export GROQ_API_KEY=gsk-exported", "gsk-exported"),
        ("GROQ_API_KEY=gsk-plain  # production", "gsk-plain"),
        ('GROQ_API_KEY="gsk-quoted"', "gsk-quoted"),
        ("GROQ_API_KEY='gsk-single'", "gsk-single"),
    ],
)
def test_parses_the_dotenv_forms_that_silently_misconfigured_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str, expected: str
) -> None:
    """Each of these previously produced a non-empty but wrong value, which
    passes the presence check and then fails authentication with an opaque
    401 rather than a configuration error."""
    env_file = tmp_path / ".env"
    env_file.write_text(line + "\n")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("AUGURY_ENV_FILE", str(env_file))

    assert load_settings().api_key == expected


def test_a_variable_outside_the_allowlist_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file may not be ours."""
    import os

    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=gsk-x\nLD_PRELOAD=/tmp/evil.so\n")
    monkeypatch.delenv("LD_PRELOAD", raising=False)
    monkeypatch.setenv("AUGURY_ENV_FILE", str(env_file))

    load_settings()

    assert "LD_PRELOAD" not in os.environ
