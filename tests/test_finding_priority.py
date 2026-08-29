"""Ordering findings by something other than the model's opinion of them.

Anchoring severity to reachability moved 92 high findings to 87. It was the
wrong fix for the right problem: nearly every finding sits on the request path,
so reachability cannot separate them, and the model calls almost everything
high because nothing anchors the word.

Severity from a language model is not a measurement. These four things are:
whether the finding carries a claim an experiment could settle, how far it is
from an entrypoint, how many modules depend on the file, and whether the
specialist showed its arithmetic. Ordering by those gives a list whose top is
worth reading first, whatever the model called each one.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.priority import rank
from augury.core.schemas import Comparator, Prediction


def _finding(
    *,
    path: str = "a.py",
    severity: Severity = Severity.MEDIUM,
    prediction: Prediction | None = None,
    arithmetic: str = "",
) -> Finding:
    return Finding(
        path=path,
        line=1,
        layer="data",
        symbol="handler",
        mechanism="Something happens under load.",
        severity=severity,
        remediation="Change it.",
        prediction=prediction,
        arithmetic=arithmetic,
    )


PREDICTION = Prediction(
    metric="queries_per_request",
    comparator=Comparator.AT_LEAST,
    value=51,
    unit="queries",
    condition="50 rows",
)


def test_a_testable_claim_outranks_an_untestable_one() -> None:
    """The whole thesis of this project, applied to its own output."""
    testable = _finding(path="a.py", prediction=PREDICTION)
    prose = _finding(path="b.py")

    ordered = rank([prose, testable], depths={"a.py": 0, "b.py": 0}, fan_in={})

    assert ordered[0] is testable


def test_the_request_path_outranks_the_far_side_of_the_graph() -> None:
    near = _finding(path="near.py")
    far = _finding(path="far.py")

    ordered = rank([far, near], depths={"near.py": 0, "far.py": 6}, fan_in={})

    assert ordered[0] is near


def test_a_file_many_modules_depend_on_outranks_a_leaf() -> None:
    hub = _finding(path="hub.py")
    leaf = _finding(path="leaf.py")

    ordered = rank([leaf, hub], depths={"hub.py": 1, "leaf.py": 1}, fan_in={"hub.py": 30})

    assert ordered[0] is hub


def test_shown_arithmetic_outranks_an_assertion() -> None:
    shown = _finding(path="a.py", arithmetic="8 workers against a pool of 5")
    asserted = _finding(path="b.py")

    ordered = rank([asserted, shown], depths={"a.py": 0, "b.py": 0}, fan_in={})

    assert ordered[0] is shown


def test_the_model_s_severity_breaks_ties_and_does_not_decide_them() -> None:
    """It is evidence, just the weakest kind here."""
    high_but_untestable = _finding(path="a.py", severity=Severity.HIGH)
    low_but_testable = _finding(path="b.py", severity=Severity.LOW, prediction=PREDICTION)

    ordered = rank(
        [high_but_untestable, low_but_testable], depths={"a.py": 0, "b.py": 0}, fan_in={}
    )

    assert ordered[0] is low_but_testable


def test_ranking_is_stable_for_findings_that_tie_on_everything() -> None:
    """Two runs of one report must not reorder, or a diff is noise."""
    findings = [_finding(path=name) for name in ("c.py", "a.py", "b.py")]
    depths = dict.fromkeys(("a.py", "b.py", "c.py"), 0)

    once = [f.path for f in rank(findings, depths=depths, fan_in={})]
    twice = [f.path for f in rank(findings, depths=depths, fan_in={})]

    assert once == twice == ["a.py", "b.py", "c.py"]
