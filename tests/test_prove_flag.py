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


def test_the_report_command_actually_calls_the_proving_pass() -> None:
    """The flag existed, was documented, and was wired to nothing.

    `--prove 2` ran a full review and printed no proving output at all: the
    call had been inserted into the `--case` branch instead of the repository
    one. Both accept the flag, so nothing failed and nothing happened -- the
    same shape as the `--prove` that was accepted and ignored before, and as
    `AUGURY_REPLAY_ONLY` being documented for weeks while nothing read it.

    Checked by reading the source, because the alternative is a live review.
    """
    import ast
    from pathlib import Path

    source = Path("src/augury/cli/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    report_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "report"
    )
    called = {
        node.func.id
        for node in ast.walk(report_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_settle" in called, "report accepts --prove and never proves anything"
