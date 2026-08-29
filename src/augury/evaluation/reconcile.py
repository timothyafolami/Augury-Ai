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
from augury.core.schemas import Comparator

_SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}

# The field limits a merged finding must still satisfy.
MAX_MECHANISM = 4000
MAX_LAYER = 60


def reconcile(report: DraftReport) -> DraftReport:
    """One finding per construct, keeping the strongest of each part."""
    by_construct: dict[tuple[str, str], list[DraftFinding]] = {}
    for finding in report.findings:
        by_construct.setdefault((finding.path, finding.symbol), []).append(finding)

    return DraftReport(
        findings=[merged for group in by_construct.values() for merged in _split(group)]
    )


def _split(group: list[DraftFinding]) -> list[DraftFinding]:
    """One finding per measurable consequence of a construct.

    Two specialists predicting different metrics about the same function are
    two findings, not one. Merging them discarded the only metric the case
    could actually run and kept one with no experiment, guaranteeing Broken.

    A finding with no prediction is not a separate consequence; it joins the
    others when there is exactly one metric to join, and stands alone only
    when there is nothing to attach it to.
    """
    by_metric: dict[str, list[DraftFinding]] = {}
    for finding in group:
        metric = finding.prediction.metric if finding.prediction else ""
        by_metric.setdefault(metric, []).append(finding)

    unfalsifiable = by_metric.pop("", [])
    if not by_metric:
        return [_merge(unfalsifiable)]
    if len(by_metric) == 1:
        only = next(iter(by_metric))
        by_metric[only] = by_metric[only] + unfalsifiable
    else:
        # Several metrics and no way to say which the prose belongs to, so it
        # is kept rather than arbitrarily attached to one of them.
        return [_merge(members) for members in by_metric.values()] + (
            [_merge(unfalsifiable)] if unfalsifiable else []
        )

    return [_merge(members) for members in by_metric.values()]


def _merge(group: list[DraftFinding]) -> DraftFinding:
    if len(group) == 1:
        return group[0]

    return group[0].model_copy(
        update={
            # Agreement across concerns is evidence, so every specialist that
            # raised it is credited rather than silently dropped.
            "layer": "+".join(sorted({finding.layer for finding in group}))[:MAX_LAYER],
            "severity": max(group, key=lambda f: _SEVERITY_ORDER[f.severity]).severity,
            # Bounded: eight specialists' prose concatenated overflowed the
            # field length, raised, and zeroed an entire arm-seed -- which
            # then read as a genuine miss rather than a harness failure.
            "mechanism": " ".join(
                dict.fromkeys(finding.mechanism for finding in group if finding.mechanism)
            )[:MAX_MECHANISM],
            "remediation": max(group, key=lambda f: len(f.remediation)).remediation,
            "arithmetic": max(group, key=lambda f: len(f.arithmetic)).arithmetic,
            "prediction": _strictest(group),
            "line": min(finding.line for finding in group),
        }
    )


def _strictest(group: list[DraftFinding]) -> DraftPrediction | None:
    """The most informative claim among those offered.

    A finding with a prediction always beats one without: keeping the version
    with no prediction would throw away the only testable claim.

    Between two predictions of the same metric, strictness depends on the
    comparator. A larger threshold is stricter for AT_LEAST and weaker for
    AT_MOST, and taking the maximum in both directions silently upgraded a
    Miss into a Hit.
    """
    predictions = [f.prediction for f in group if f.prediction is not None]
    if not predictions:
        return None

    if predictions[0].comparator is Comparator.AT_MOST:
        return min(predictions, key=lambda p: p.value)
    if predictions[0].comparator is Comparator.BETWEEN:
        return min(predictions, key=lambda p: (p.upper or p.value) - p.value)
    return max(predictions, key=lambda p: p.value)
