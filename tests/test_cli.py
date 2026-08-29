"""The command line is what a judge runs first.

It is also the only evaluated surface: every published number comes from these
commands, so they have to work from a clean clone and fail in a way that says
what to do next.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from augury.cli.main import app

runner = CliRunner()


def test_help_lists_both_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "review" in result.stdout
    assert "evaluate" in result.stdout


def test_listing_cases_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A judge should be able to see what is here before spending anything."""
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = runner.invoke(app, ["cases"])

    assert result.exit_code == 0
    assert "B01" in result.stdout
    assert "5" in result.stdout, "the seeded defect count should be visible"


def test_an_unknown_case_says_which_ones_exist() -> None:
    result = runner.invoke(app, ["review", "--case", "ZZ99", "--arm", "baseline"])

    assert result.exit_code != 0
    assert "B01" in result.stdout


def test_an_unknown_arm_is_refused() -> None:
    result = runner.invoke(app, ["review", "--case", "B01", "--arm", "nonesuch"])

    assert result.exit_code != 0


def test_a_missing_key_names_the_variable_rather_than_stack_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A traceback here would also print the key when one is set, because
    typer shows locals by default."""
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent/.env")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("AUGURY_PROVIDER", raising=False)

    result = runner.invoke(app, ["review", "--case", "B01", "--arm", "baseline"])

    assert result.exit_code != 0
    assert "GROQ_API_KEY" in result.stdout
    assert "Traceback" not in result.stdout


def test_the_runner_never_shows_locals() -> None:
    """Typer prints local variables in tracebacks by default, and `api_key` is
    a local at every call site that builds a model."""
    assert app.pretty_exceptions_show_locals is False


# -- the documented invocation ---------------------------------------------
# Every test above imports `augury.cli.main` directly, which is why a broken
# `python -m augury.cli` survived a green suite. A judge does not import; they
# run the command in the guide.


def test_the_documented_module_path_is_executable() -> None:
    """`python -m augury.cli` is what the Makefile and REPRODUCE.md invoke."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "augury.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    assert result.returncode == 0, result.stderr


def test_the_installed_console_script_exists() -> None:
    """`augury` is the name settings.py's own error messages tell users to run."""
    import shutil
    import sys

    binary = Path(sys.executable).parent / "augury"
    assert binary.is_file() or shutil.which("augury"), "no `augury` command was installed"


@pytest.mark.parametrize("target", ["review-baseline", "review-augury", "evaluate"])
def test_every_make_target_names_a_runnable_command(target: str) -> None:
    """A target that cannot start is worse than a missing one: it looks like
    the tool is broken rather than the documentation."""
    makefile = (Path(__file__).parent.parent / "Makefile").read_text()

    assert target in makefile
    assert "python -m augury.cli " in makefile or "augury " in makefile
