"""One over-long sentence destroyed a paid run at its final step.

`DraftFinding` declares no length limits, so nothing stops a specialist
writing a thorough mechanism. `Finding.mechanism` is capped at 4096, and
`to_report` constructs one without truncating or catching -- after the whole
scheduler loop has run and the whole budget is spent.

The CLI's only handler around that call reports provider failures, so the user
is told the model refused the request. And the memo has already stored the
draft, so every later run recalls it and dies identically, for free, until
--no-cache.

reconcile.py fixed this once, with MAX_MECHANISM = 4000 and a comment naming
the same failure -- but it returns a single-member group unchanged, so one long
mechanism from one specialist bypasses it.
"""

from __future__ import annotations

from augury.core.drafts import DraftFinding, DraftReport, to_report


def _draft(**over: object) -> DraftFinding:
    fields: dict[str, object] = {
        "path": "app/api.py",
        "line": 1,
        "layer": "network",
        "symbol": "handler",
        "mechanism": "It does something slow.",
        "remediation": "Do it faster.",
        "severity": "high",
        "arithmetic": "",
        "prediction": None,
    }
    fields.update(over)
    return DraftFinding(**fields)  # type: ignore[arg-type]


def test_an_over_long_mechanism_becomes_a_finding_rather_than_an_exception() -> None:
    report = to_report(DraftReport(findings=[_draft(mechanism="x" * 4721)]))

    assert len(report.findings) == 1


def test_the_truncated_mechanism_says_it_was_truncated() -> None:
    report = to_report(DraftReport(findings=[_draft(mechanism="x" * 4721)]))

    assert "truncated" in report.findings[0].mechanism.lower()


def test_an_over_long_remediation_survives_too() -> None:
    report = to_report(DraftReport(findings=[_draft(remediation="y" * 4721)]))

    assert len(report.findings) == 1


def test_an_over_long_symbol_survives_too() -> None:
    report = to_report(DraftReport(findings=[_draft(symbol="z" * 900)]))

    assert len(report.findings) == 1


def test_an_item_that_cannot_be_repaired_is_dropped_rather_than_fatal() -> None:
    """Whatever else is malformed, one bad item must not cost the run."""
    report = to_report(DraftReport(findings=[_draft(line=-5), _draft()]))

    assert len(report.findings) + len(report.dropped) == 2
