"""What to read first, ordered by evidence rather than by adjective.

A specialist is asked for a severity and given no anchor for the word, so on a
real service it answered "high" 92 times out of 141. Capping that by
reachability moved it to 87, because nearly every finding is on the request
path: the right problem, the wrong fix.

Severity from a language model is not a measurement. Four things here are:

- whether the finding carries a claim an experiment could settle
- how far the code is from where a request arrives
- how many modules depend on the file
- whether the specialist showed the arithmetic behind its threshold

None of these says a finding is true. They say which ones can be checked, and
which ones are somewhere a failure would be felt. That is what a list to triage
needs, and the model's own adjective is kept only to break ties.
"""

from __future__ import annotations

from collections.abc import Mapping

from augury.core.findings import Finding, Severity

TESTABLE = 4.0
"""A claim an experiment can settle is worth more than one that cannot be."""

ARITHMETIC = 1.5
"""A threshold with its derivation shown is one somebody can argue with."""

SEVERITY_WEIGHT = {Severity.HIGH: 1.0, Severity.MEDIUM: 0.5, Severity.LOW: 0.0}

DEPTH_DECAY = 0.7
UNREACHABLE = 0.2


def rank(
    findings: list[Finding],
    *,
    depths: Mapping[str, int | None],
    fan_in: Mapping[str, int],
) -> list[Finding]:
    """Findings, most worth reading first. Stable for equal scores."""
    return sorted(
        findings,
        key=lambda f: (-_score(f, depths, fan_in), f.path, f.line, f.symbol),
    )


def _score(finding: Finding, depths: Mapping[str, int | None], fan_in: Mapping[str, int]) -> float:
    depth = depths.get(finding.path)
    reach = UNREACHABLE if depth is None else DEPTH_DECAY**depth
    blast = 1.0 + fan_in.get(finding.path, 0) / 10.0

    evidence = 1.0
    if finding.prediction is not None:
        evidence *= TESTABLE
    if finding.arithmetic.strip():
        evidence *= ARITHMETIC

    return evidence * reach * blast + SEVERITY_WEIGHT[finding.severity]
