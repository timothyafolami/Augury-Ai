"""Three ways the review claimed more than it did.

Each is small on its own; together they are the same fault, which is that the
numbers the report exists to state honestly were computed from a path where
something had gone missing.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.reachability import cap_severity


def _finding(path: str) -> Finding:
    return Finding(
        path=path,
        line=1,
        layer="security",
        symbol="verify",
        mechanism="The JWT signature is not verified, so any token is accepted.",
        remediation="Verify it.",
        severity=Severity.HIGH,
    )


def test_a_path_the_map_never_had_is_not_called_unreachable() -> None:
    """`depths.get(path)` returns None for "not in the map" and for "no
    entrypoint reaches it", and only the second is a measurement.

    A model that omits the path gets `path = "unknown"`, which is in no map, so
    a HIGH security finding was demoted to LOW and stamped with the sentence
    "no entrypoint reaches this module" -- a fact asserted about a module that
    does not exist.
    """
    capped = cap_severity(_finding("unknown"), depth=None, known=False)

    assert capped.severity is Severity.HIGH
    assert "no entrypoint reaches" not in capped.mechanism


def test_a_module_the_map_says_nothing_reaches_is_still_capped() -> None:
    """The behaviour this exists for, which the distinction must not cost."""
    capped = cap_severity(_finding("app/dead.py"), depth=None, known=True)

    assert capped.severity is not Severity.HIGH


def test_a_reachable_module_is_untouched() -> None:
    assert cap_severity(_finding("app/api.py"), depth=0, known=True).severity is Severity.HIGH


def test_triage_choosing_nobody_is_not_the_same_as_reading_the_module() -> None:
    """A structurally valid but empty triage answer counted as full coverage.

    `Reading.unread` covers a specialist that raised. It did not cover a
    triage model that returned an empty list of specialists -- so a provider
    whose structured output degrades under load produces a run that costs the
    triage calls, finds nothing, and reports 100% coverage.
    """
    from augury.agents.augury import Reading

    nobody = Reading.nobody_asked("app/api.py", allowed=3)

    assert not nobody.read
    assert "triage" in nobody.why


def test_the_cost_of_proving_reaches_the_report() -> None:
    """`report.usd` is fixed before proving runs, and _settle never adds to it.

    Five experiment-generation calls were paid for and published as $0.00, in
    the document whose preamble says every coverage sentence is arithmetic.
    """
    from augury.core.findings import Report

    before = Report(findings=(), model_id="m", usd=0.10, seconds=1.0)
    after = before.model_copy(update={"usd": before.usd + 0.03})

    assert after.usd == 0.13
