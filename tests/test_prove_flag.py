"""Running generated experiments is opt-in, and says so.

`--prove N` writes a script per finding and executes it against the
repository. That is a different kind of act from reading files, so it does not
happen by default and it announces itself when it does.

N rather than a boolean: findings arrive ranked, and proving 139 of them means
139 generated scripts. The top few are the ones worth settling.
"""

from __future__ import annotations

import inspect

from augury.cli.main import report, review


def test_review_and_report_both_take_a_prove_count() -> None:
    for command in (review, report):
        parameters = inspect.signature(command).parameters
        assert "prove" in parameters, f"{command.__name__} cannot prove anything"


def test_proving_is_off_unless_asked_for() -> None:
    """Executing generated code must never be a default."""
    default = inspect.signature(report).parameters["prove"].default

    assert getattr(default, "default", default) == 0


def test_the_help_says_generated_code_will_run() -> None:
    """Somebody has to be told before it happens, not after."""
    prove = inspect.signature(report).parameters["prove"].default
    help_text = getattr(prove, "help", "") or ""

    assert "generated" in help_text.lower()
    assert "run" in help_text.lower() or "execut" in help_text.lower()
