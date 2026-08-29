"""Severity, anchored to whether a request reaches the code.

A specialist is told "severity: high, medium or low" and nothing else, so the
answer is its prior. On a real service that produced 92 high out of 141
findings, which is a list rather than a triage.

The import graph knows something the specialist does not: whether an entrypoint
reaches this module, and in how many hops. A blocking call in an auth
dependency that runs on every request is not the same severity as one in a
script nothing imports, and that is a fact rather than an opinion.

Only ever lowered. The specialist read the source and this did not, so it may
call a reachable finding low and be right; it may not call an unreachable one
high, because unreachable code does not cause production incidents.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity

# Hops from an entrypoint beyond which a finding stops being where an incident
# starts. Chosen against the real repository this was built on, where the
# request path runs to depth 5 and the median finding sits at 0.
FAR_FROM_ENTRYPOINT = 4

_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def cap_severity(finding: Finding, *, depth: int | None, has_entrypoints: bool = True) -> Finding:
    """The same finding, at a severity its reachability can support."""
    if not has_entrypoints:
        # No declared entrypoint means no request path, and calling every
        # module unreachable would say nothing about any of them.
        return finding

    if depth is None:
        ceiling, why = Severity.LOW, "no entrypoint reaches this module"
    elif depth >= FAR_FROM_ENTRYPOINT:
        ceiling, why = Severity.MEDIUM, f"{depth} hops from the nearest entrypoint"
    else:
        return finding

    if _ORDER[finding.severity] <= _ORDER[ceiling]:
        return finding

    return finding.model_copy(
        update={
            "severity": ceiling,
            "mechanism": f"{finding.mechanism} (Severity lowered: {why}.)",
        }
    )
