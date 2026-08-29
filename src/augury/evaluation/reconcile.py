"""Merge findings that collide on the same construct.

Pool exhaustion is simultaneously a network, a data and a failure concern, so
three specialists can each raise it honestly. Three near-identical entries in a
report is a defect in the reviewer rather than a thorough review: it dilutes
precision, inflates the finding count, and teaches the reader to skim.

Deliberately deterministic. A rule that merges on file and symbol needs no
model call, costs nothing, and cannot hallucinate a merge that should not have
happened. A model would be the right tool only for findings that describe the
same defect in different words at different locations, which is a harder
problem and not this one.
"""

from __future__ import annotations

from augury.core.drafts import DraftFinding, DraftPrediction, DraftReport
from augury.core.findings import Severity

_SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def reconcile(report: DraftReport) -> DraftReport:
    """One finding per construct, keeping the strongest of each part."""
    grouped: dict[tuple[str, str], list[DraftFinding]] = {}
    for finding in report.findings:
        grouped.setdefault((finding.path, finding.symbol), []).append(finding)

    return DraftReport(findings=[_merge(group) for group in grouped.values()])


def _merge(group: list[DraftFinding]) -> DraftFinding:
    if len(group) == 1:
        return group[0]

    return group[0].model_copy(
        update={
            # Agreement across concerns is evidence, so every specialist that
            # raised it is credited rather than silently dropped.
            "layer": "+".join(sorted({finding.layer for finding in group})),
            "severity": max(group, key=lambda f: _SEVERITY_ORDER[f.severity]).severity,
            "mechanism": " ".join(
                dict.fromkeys(finding.mechanism for finding in group if finding.mechanism)
            ),
            "remediation": max(group, key=lambda f: len(f.remediation)).remediation,
            "arithmetic": max(group, key=lambda f: len(f.arithmetic)).arithmetic,
            "prediction": _strictest(group),
            "line": min(finding.line for finding in group),
        }
    )


def _strictest(group: list[DraftFinding]) -> DraftPrediction | None:
    """The most informative claim among those offered.

    A finding with a prediction always beats one without: keeping the version
    with no prediction would throw away the only testable claim. Between two
    predictions, the stricter threshold excludes more of the outcome space and
    is therefore both more informative and easier to refute.
    """
    predictions = [f.prediction for f in group if f.prediction is not None]
    if not predictions:
        return None
    return max(predictions, key=lambda p: p.value)
