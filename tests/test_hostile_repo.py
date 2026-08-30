"""Augury is pointed at repositories it does not trust. That is the job.

A code-review tool's input is, by definition, attacker-controlled whenever the
attacker wants it to be. These tests pin the boundary: what a hostile
repository must not be able to do to the process reviewing it.
"""

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from augury.core.cartography import Cartographer
from augury.core.settings import load_settings
from tests.test_churn import git


def test_a_reviewed_repository_cannot_set_our_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The obvious invocation is `cd untrusted-repo && augury review .`.

    If that repo's .env is loaded, it can set AUGURY_TEMPERATURE=2 to degrade
    the review into noise, or AUGURY_REPLAY_ONLY=1 to make the tool serve stale
    answers instead of reviewing it at all. That is the cheapest possible way
    for a repository to escape scrutiny.
    """
    (tmp_path / ".env").write_text("AUGURY_TEMPERATURE=2\nAUGURY_REPLAY_ONLY=1\n")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.delenv("AUGURY_TEMPERATURE", raising=False)
    monkeypatch.delenv("AUGURY_REPLAY_ONLY", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.spec.temperature == 0.0
    assert settings.replay_only is False


def test_a_reviewed_repository_cannot_inject_arbitrary_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIT_CONFIG_* and LD_PRELOAD are normally unset, therefore injectable,
    and are inherited by the git subprocess."""
    (tmp_path / ".env").write_text(
        "LD_PRELOAD=/tmp/evil.so\nGIT_CONFIG_COUNT=1\nGIT_EXTERNAL_DIFF=/tmp/evil\n"
    )
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    for name in ("LD_PRELOAD", "GIT_CONFIG_COUNT", "GIT_EXTERNAL_DIFF"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    load_settings()

    assert "LD_PRELOAD" not in os.environ
    assert "GIT_CONFIG_COUNT" not in os.environ
    assert "GIT_EXTERNAL_DIFF" not in os.environ


def test_a_symlink_out_of_the_repository_is_not_read(tmp_path: Path) -> None:
    """`config.py -> ~/.aws/credentials` reads the target into our process,
    and a .env symlinked as config.py is largely valid Python, so it parses
    and survives into a prompt."""
    repo = tmp_path / "repo"
    repo.mkdir()
    secret = tmp_path / "outside.env"
    secret.write_text("GROQ_API_KEY = 'gsk_real_secret_value'\n")
    (repo / "config.py").symlink_to(secret)
    (repo / "real.py").write_text("x = 1\n")

    mapped = Cartographer(repo).map()

    assert [m.path for m in mapped.modules] == ["real.py"]


def test_an_enormous_file_is_not_read_into_memory(tmp_path: Path) -> None:
    """No size cap means one file can exhaust memory, and a binary shipped
    with a source extension becomes replacement-character soup that is then
    tokenised at cost."""
    (tmp_path / "small.py").write_text("x = 1\n")
    (tmp_path / "huge.py").write_text("# padding\n" * 200_000)

    mapped = Cartographer(tmp_path).map()

    assert [m.path for m in mapped.modules] == ["small.py"]
    assert "huge.py" in mapped.skipped


def test_churn_decodes_raw_git_filename_bytes_on_every_filesystem(tmp_path: Path) -> None:
    """Git gives this boundary bytes, even where the local filesystem will not."""
    output = b"app.py\nweird_\xff_name.py\n"
    completed = subprocess.CompletedProcess(args=["git"], returncode=0, stdout=output)

    with mock.patch("augury.core.cartography.mapper.subprocess.run", return_value=completed):
        churn = Cartographer(tmp_path)._churn()

    assert churn == {"app.py": 1, os.fsdecode(b"weird_\xff_name.py"): 1}


def test_a_filename_that_is_not_valid_utf8_does_not_crash_the_review(
    tmp_path: Path,
) -> None:
    """Git log output can contain filename bytes that are not valid UTF-8.

    An untrusted repository can contain such a name trivially, and
    strict decoding would take down the whole review before the churn handler
    could return its normal best-effort result.
    """
    git(tmp_path, "init", "-q")
    (tmp_path / "app.py").write_text("x = 1\n")
    try:
        (tmp_path / os.fsdecode(b"weird_\xff_name.py")).write_text("y = 1\n")
    except (OSError, UnicodeError):  # pragma: no cover - filesystem dependent
        pytest.skip("filesystem rejects non-UTF-8 names")

    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x")

    mapped = Cartographer(tmp_path).map()

    assert mapped.module("app.py").loc == 1
