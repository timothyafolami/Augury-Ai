"""A layer whose mechanism has no metric cannot be predicted about.

The vocabulary is fixed on purpose, because a reviewer left to invent names
produces `db_queries_per_list_orders` where the harness ships
`queries_per_request` and every prediction comes back Broken. But a fixed
vocabulary is also a ceiling: the audit against the practice lab found several
layers largely inexpressible rather than merely uncovered, because the number
their mechanism is about had no name.

Naming one here does not promise a case can measure it. A prediction about a
metric no experiment settles is Broken, which is honest and is the reviewer's
information to have. Being unable to state the claim at all is not.
"""

from __future__ import annotations

from augury.core.metrics import METRICS


def test_a_cpu_quota_freeze_can_be_stated() -> None:
    """Layer 1e. Eight threads drain a one-CPU quota in 12.5ms of a 100ms
    period, and the container is stopped for the rest. Without a throttle
    figure the whole layer is unclaimable."""
    assert "throttled_share" in METRICS


def test_replication_lag_can_be_stated() -> None:
    """03-data/08. A read replica makes stale reads supported behaviour, and
    the lab measures the gap in bytes rather than in seconds."""
    assert "replication_lag_bytes" in METRICS


def test_goodput_can_be_stated_apart_from_throughput() -> None:
    """05-failure/04. The signature of metastable failure is throughput
    holding while goodput collapses, so one number cannot carry both."""
    assert "goodput" in METRICS
    assert "throughput_rps" in METRICS


def test_file_descriptors_can_be_stated() -> None:
    """01-machine/06. A leak surfaces as EMFILE far from its cause."""
    assert "open_file_descriptors" in METRICS


def test_a_cache_hit_rate_can_be_stated() -> None:
    assert "cache_hit_rate" in METRICS


def test_the_wait_before_a_statement_can_be_stated() -> None:
    """06-observability/05. Once a pool pins at full, checkout wait is the
    only number still moving, and it produces no span."""
    assert "pool_wait_ms" in METRICS


def test_every_metric_says_what_it_counts_and_in_what_unit() -> None:
    """A name with no unit is the ambiguity this vocabulary exists to remove.

    A description may open with a figure -- "99th percentile request latency"
    is the natural way to say that one -- so this asserts it reads as a
    sentence rather than that it opens with a letter.
    """
    for name, said in METRICS.items():
        assert said.strip(), name
        assert said[0].isupper() or said[0].isdigit(), f"{name}: {said}"
        assert len(said.split()) >= 4, f"{name} says too little: {said}"


def test_the_vocabulary_stays_small_enough_to_read() -> None:
    """It is in every prompt to both arms. A list nobody finishes reading is a
    list a reviewer picks the first plausible entry from."""
    assert len(METRICS) <= 24
