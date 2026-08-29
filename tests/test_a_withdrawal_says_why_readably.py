"""Why a claim was withdrawn is the most useful line the reviewer prints.

It is the difference between "the model said nothing about this file" and
"the model made a claim that could not be falsified, and here is the rule it
broke". On a real run it printed, dozens of times:

    [dim]withdrawn get_current_user: : Value error, upper bound must exceed
    the lower bound, or nothing can Hit[/dim]

Three faults in one line: literal markup tags, a colon with nothing before it,
and Pydantic's "Value error," prefix, which names the library rather than the
problem.
"""

from __future__ import annotations

from pydantic import ValidationError

from augury.core.drafts import why_it_failed
from augury.core.schemas import Prediction


def _rejection(**fields: object) -> ValidationError:
    try:
        Prediction(**fields)  # type: ignore[arg-type]
    except ValidationError as caught:
        return caught
    raise AssertionError("that prediction was accepted")


def test_a_whole_model_rule_has_no_field_to_name_and_names_none() -> None:
    """The band check is a rule about the pair, so `loc` is empty."""
    said = why_it_failed(
        _rejection(
            metric="p99_latency_ms",
            comparator="between",
            value=10.0,
            upper=1.0,
            unit="ms",
            condition="at 100rps",
        )
    )

    assert not said.startswith(":")
    assert "upper bound must exceed" in said


def test_the_library_that_raised_is_not_the_problem() -> None:
    said = why_it_failed(
        _rejection(
            metric="p99_latency_ms",
            comparator="between",
            value=10.0,
            upper=1.0,
            unit="ms",
            condition="at 100rps",
        )
    )

    assert "Value error" not in said


def test_a_field_that_is_wrong_is_still_named() -> None:
    """Dropping the prefix must not drop the field when there is one."""
    said = why_it_failed(_rejection(metric="", comparator="nonsense", unit="ms", condition="x"))

    assert "comparator" in said


def test_the_line_is_dim_rather_than_saying_the_word_dim() -> None:
    """`markup=False` keeps a finding's text safe and prints the tags literally.

    Rich takes a style as an argument, which does both: the reason is never
    interpreted as markup, and the line is still dim.
    """
    import ast
    from pathlib import Path

    source = Path("src/augury/cli/main.py").read_text(encoding="utf-8")
    assert "[dim]withdrawn" not in source, "the tag is printed, not applied"

    # And the call that replaced it still passes a style.
    tree = ast.parse(source)
    styled = any(
        isinstance(node, ast.Call)
        and any(kw.arg == "style" for kw in node.keywords)
        and any(
            isinstance(arg, ast.JoinedStr)
            and any(isinstance(v, ast.Constant) and "withdrawn" in str(v.value) for v in arg.values)
            for arg in node.args
        )
        for node in ast.walk(tree)
    )
    assert styled, "the withdrawal line lost its dim styling"
