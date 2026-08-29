"""What a prediction is allowed to be about.

A reviewer left to invent metric names produces `db_queries_per_list_orders`
where the harness ships `queries_per_request`: the same claim, untestable for
want of a shared word. Measured on case B01 before this existed, every
prediction from both arms came back Broken and hit rate could not be computed
at all.

So the vocabulary is fixed, published to every arm, and identical for every
case regardless of what that case seeds. Identical because it must be fair, and
case-independent because a per-case list would tell the reviewer which defect
to look for.

Naming a metric here does not promise a given case can measure it. A case ships
the experiments it can run; a prediction about anything else is Broken, which
is honest and is the reviewer's information to have.
"""

from __future__ import annotations

from types import MappingProxyType

METRICS: MappingProxyType[str, str] = MappingProxyType(
    {
        "queries_per_request": "Database statements issued while serving one request",
        "http_req_duration_p99": "99th percentile request latency, in milliseconds",
        "http_status": "The status code a client receives under a stated condition",
        "final_balance": "The value of a record after a stated set of concurrent operations",
        "duplicate_side_effects": ("How many times an effect was applied for one logical request"),
        "retry_amplification": (
            "Requests reaching a dependency per request from the client, as a multiple"
        ),
        "worker_saturation": "Share of workers blocked, from 0 to 1",
        "active_connections": "Connections checked out of a pool at once",
        "queue_depth": "Items waiting to be processed",
        "memory_bytes": "Resident memory held by the process",
    }
)


def vocabulary() -> str:
    """The metric list, formatted for a prompt."""
    return "\n".join(f"- `{name}`: {meaning}" for name, meaning in METRICS.items())


def describe(conditions: dict[str, str]) -> str:
    """The experiments a case can run, and the scenario each one runs.

    Published to every arm. A reviewer cannot guess a harness's parameters,
    and a prediction about a scenario that was never run is scored on
    something other than its own correctness.
    """
    if not conditions:
        return "(this repository ships no experiments, so no claim about it can be settled)"
    return "\n".join(f"- `{metric}`: {scenario}" for metric, scenario in sorted(conditions.items()))
