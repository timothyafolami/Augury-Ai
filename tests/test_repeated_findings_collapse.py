"""One defect reported sixteen times is one defect.

"Correlation identifiers are not propagated" is true of a service, not of a
file, so a per-file reviewer reports it once per file it reads. On a real run
that was 16 of 141 findings saying the same sentence about 16 different route
handlers.

Collapsing them is not hiding them: the finding is kept, with every location it
was seen at, and the count is the evidence that it is systemic rather than
local. What it stops is one observation being counted sixteen times in a list
somebody has to triage.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.repetition import collapse


def _finding(path: str, mechanism: str, symbol: str = "handler") -> Finding:
    return Finding(
        path=path,
        line=1,
        layer="observability",
        symbol=symbol,
        mechanism=mechanism,
        severity=Severity.HIGH,
        remediation="Propagate the incoming request id.",
    )


SYSTEMIC = "Correlation identifiers are not propagated, so logs for one request cannot be gathered."


def test_the_same_mechanism_across_many_files_becomes_one_finding() -> None:
    findings = [_finding(f"app/routes/r{n}.py", SYSTEMIC) for n in range(16)]

    collapsed, _ = collapse(findings)

    assert len(collapsed) == 1
    assert "16 files" in collapsed[0].mechanism


def test_the_collapsed_finding_keeps_where_it_was_seen() -> None:
    findings = [_finding(f"app/routes/r{n}.py", SYSTEMIC) for n in range(3)]

    collapsed, _ = collapse(findings)

    assert collapsed[0].path == "app/routes/r0.py"
    for path in ("r1.py", "r2.py"):
        assert path in collapsed[0].mechanism


def test_two_files_is_not_systemic() -> None:
    """Two is a coincidence. The threshold exists so it is not a judgement."""
    findings = [_finding(f"app/routes/r{n}.py", SYSTEMIC) for n in range(2)]

    assert len(collapse(findings)[0]) == 2


def test_different_mechanisms_are_left_alone() -> None:
    findings = [
        _finding("a.py", "The pool is smaller than the worker count."),
        _finding("b.py", "The retry has no budget and no jitter."),
        _finding("c.py", "The session is held across a network call."),
    ]

    assert len(collapse(findings)[0]) == 3


def test_the_same_mechanism_in_one_file_is_not_collapsed() -> None:
    """Two call sites in one file are two things to fix, in one place."""
    findings = [
        _finding("a.py", SYSTEMIC, symbol="first"),
        _finding("a.py", SYSTEMIC, symbol="second"),
    ]

    assert len(collapse(findings)[0]) == 2


def test_wording_that_differs_only_in_the_file_it_names_still_collapses() -> None:
    """A specialist names the symbol it was looking at, so the sentences differ."""
    findings = [
        _finding("app/routes/orders.py", "list_orders does not propagate a correlation id."),
        _finding("app/routes/users.py", "list_users does not propagate a correlation id."),
        _finding("app/routes/plans.py", "list_plans does not propagate a correlation id."),
    ]

    assert len(collapse(findings)[0]) == 1
