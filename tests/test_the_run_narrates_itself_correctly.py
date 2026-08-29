"""What the run says while it works is what a reader sees of the reasoning.

Two defects visible in the first twenty lines of a recorded run: it counted
"1 entrypoints", and it announced stages 1 through 4 of 5 and then stopped,
so the last thing before the output was a stage that never said it had begun.
"""

from __future__ import annotations

import ast
from pathlib import Path

from augury.cli.banner import counted


def test_one_of_something_is_singular() -> None:
    assert counted(1, "entrypoint") == "1 entrypoint"


def test_several_are_plural() -> None:
    assert counted(3, "entrypoint") == "3 entrypoints"


def test_none_is_plural() -> None:
    """ "0 entrypoints", the way English does it, not "0 entrypoint"."""
    assert counted(0, "entrypoint") == "0 entrypoints"


def test_a_word_with_its_own_plural_is_given_one() -> None:
    assert counted(2, "service", plural="services") == "2 services"


def test_a_large_count_is_grouped_for_reading() -> None:
    """29576 lines is a number nobody reads at a glance."""
    assert counted(29576, "line") == "29,576 lines"


def test_every_stage_the_run_promises_is_announced() -> None:
    """It said "1/5" through "4/5" and then printed the output.

    Read from the source rather than from a run, because reaching stage five
    costs a review. If the announced total and the number of announcements
    disagree, one of them is a lie.
    """
    source = Path("src/augury/cli/main.py").read_text(encoding="utf-8")

    announced: list[tuple[int, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not (isinstance(target, ast.Attribute) and target.attr == "stage"):
            continue
        numbers = [a.value for a in node.args if isinstance(a, ast.Constant)]
        pair = [n for n in numbers[:2] if isinstance(n, int)]
        if len(pair) == 2:
            announced.append((pair[0], pair[1]))

    assert announced, "no stages are announced at all"
    total = announced[0][1]
    assert sorted(n for n, _ in announced) == list(range(1, total + 1)), (
        f"promised {total} stages, announced {sorted(n for n, _ in announced)}"
    )
