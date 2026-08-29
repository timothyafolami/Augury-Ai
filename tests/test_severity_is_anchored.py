"""Severity has to mean something, and the model has no basis for it.

The entire instruction is "`severity`: high, medium or low", so the answer is
the model's prior rather than a judgement. On a real service that produced 92
high out of 141 findings, which is not a triage.

The harness knows something the model does not: whether a request reaches this
code, and how soon. A defect in an auth dependency that runs on every request
is not the same severity as one in a script no entrypoint imports, and that
difference is a fact about the import graph rather than an opinion.

So severity is capped by reachability. Capped, never raised: the model may
still say a reachable finding is low, because it can see the code and the
graph cannot.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.reachability import cap_severity


def _finding(severity: Severity) -> Finding:
    return Finding(
        path="app/api/deps.py",
        line=1,
        layer="network",
        symbol="get_current_user",
        mechanism="Blocking call in an async dependency.",
        severity=severity,
        remediation="Offload it.",
    )


def test_a_finding_on_the_request_path_keeps_its_severity() -> None:
    assert cap_severity(_finding(Severity.HIGH), depth=0).severity is Severity.HIGH
    assert cap_severity(_finding(Severity.HIGH), depth=1).severity is Severity.HIGH


def test_a_finding_far_from_any_entrypoint_is_capped_at_medium() -> None:
    """Still worth reporting, and not where an incident starts."""
    assert cap_severity(_finding(Severity.HIGH), depth=6).severity is Severity.MEDIUM


def test_a_finding_no_request_reaches_is_capped_at_low() -> None:
    """Code that does not run cannot be the cause of a production failure."""
    assert cap_severity(_finding(Severity.HIGH), depth=None).severity is Severity.LOW


def test_severity_is_only_ever_lowered() -> None:
    """The model can see the code; the import graph cannot.

    A low finding on the request path stays low. Promoting it would mean the
    graph overruling the only thing that read the source.
    """
    assert cap_severity(_finding(Severity.LOW), depth=0).severity is Severity.LOW
    assert cap_severity(_finding(Severity.MEDIUM), depth=0).severity is Severity.MEDIUM


def test_capping_says_why_in_the_mechanism() -> None:
    """A severity that was lowered must say so, or it looks like a judgement."""
    capped = cap_severity(_finding(Severity.HIGH), depth=None)

    assert "no entrypoint reaches" in capped.mechanism


def test_an_unknown_depth_in_a_repository_with_no_entrypoints_changes_nothing() -> None:
    """A library declares no request path, so reachability says nothing at all."""
    unchanged = cap_severity(_finding(Severity.HIGH), depth=None, has_entrypoints=False)

    assert unchanged.severity is Severity.HIGH
    assert unchanged.mechanism == _finding(Severity.HIGH).mechanism
