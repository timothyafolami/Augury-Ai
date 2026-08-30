"""What the gate rejects, the prompt has to say -- to both arms equally.

On one real run, 8 of about 53 predictions were withdrawn for the same reason:
`upper` was not above `value`. The prompt named the two fields and never said
which had to be larger, so a rejected claim was a claim the reviewer was never
told how to write.

The rule that makes this safe: whatever is added here is added to the baseline
prompt too. An analyst told what the validator enforces while the baseline is
not is the arm asymmetry this project already fixed once, and
tests/test_arm_symmetry_beyond_bytes.py exists because of it.
"""

from __future__ import annotations

from pathlib import Path

ANALYST = Path("src/augury/prompts/analyst.md").read_text(encoding="utf-8")
BASELINE = Path("src/augury/prompts/baseline.md").read_text(encoding="utf-8")


def test_the_analyst_is_told_the_upper_bound_must_be_larger() -> None:
    assert "greater than `value`" in ANALYST


def test_the_baseline_is_told_the_same_thing() -> None:
    """Coaching one arm on the validator's rules is scoring one arm's answer key."""
    assert "greater than `value`" in BASELINE


def test_the_analyst_is_told_a_threshold_must_be_reachable() -> None:
    """The gate now rejects by unit, not against zero, so the prompt must too."""
    assert "at least 1" in ANALYST or "below what anything measures" in ANALYST


def test_the_baseline_is_told_that_too() -> None:
    assert "at least 1" in BASELINE or "below what anything measures" in BASELINE
