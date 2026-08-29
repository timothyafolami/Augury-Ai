"""Saying why an experiment could not run, not merely that it did not.

Proving a finding on a real repository returned "broken: printed no number"
three times. The cause was one line of stderr: `ModuleNotFoundError: No module
named 'jwt'`. The dependencies live in the Docker image the compose file
builds, and no local interpreter has them.

"Printed no number" is true and useless. "Your dependencies are not installed
in the interpreter I could find, and your services build from a Dockerfile" is
the same fact, said in a way somebody can act on.
"""

from __future__ import annotations

from augury.core.proving.diagnosis import diagnose

MISSING = (
    "Traceback (most recent call last):\n"
    '  File "/tmp/x.py", line 3, in <module>\n'
    "    import jwt\n"
    "ModuleNotFoundError: No module named 'jwt'\n"
)


def test_a_missing_dependency_is_named() -> None:
    said = diagnose(MISSING, interpreter="/repo/.conda/bin/python")

    assert "jwt" in said
    assert ".conda" in said


def test_it_says_the_dependency_belongs_to_the_repository() -> None:
    """The distinction that makes it actionable rather than a shrug."""
    said = diagnose(MISSING, interpreter="/repo/.conda/bin/python").lower()

    assert "not installed" in said


def test_an_import_error_from_the_repository_itself_is_different() -> None:
    """`No module named 'app'` is a path problem, not a dependency problem."""
    said = diagnose(
        "ModuleNotFoundError: No module named 'app.services'",
        interpreter="/repo/.venv/bin/python",
    ).lower()

    assert "importable" in said or "path" in said


def test_a_syntax_error_in_the_generated_script_says_so() -> None:
    said = diagnose(
        'File "/tmp/x.py", line 4\n    def (\nSyntaxError: invalid syntax',
        interpreter="/x/python",
    ).lower()

    assert "generated" in said


def test_an_unrecognised_failure_returns_the_tail_rather_than_a_guess() -> None:
    """Inventing a cause is worse than quoting the error."""
    said = diagnose("RuntimeError: the flux capacitor is misaligned", interpreter="/x/python")

    assert "flux capacitor" in said


def test_no_stderr_at_all_says_that() -> None:
    assert "no error output" in diagnose("", interpreter="/x/python").lower()
