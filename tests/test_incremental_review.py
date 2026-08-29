"""Not paying twice to read a file that has not changed.

A review of a real backend is 167 modules and several minutes. Run it again
after editing three files and 164 of those calls buy the answer they bought
last time, at the same cost and against the same tokens-per-minute ceiling that
is the actual constraint.

The key is the content, the specialist, the language and the prompt itself. A
changed prompt is a different question, so it must miss -- the same argument as
the model cassettes, one layer up: a cache that serves a stale answer to a new
question is worse than no cache.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.drafts import DraftFinding, DraftReport
from augury.core.findings import Severity
from augury.core.memo import Memo


def _draft(symbol: str) -> DraftReport:
    return DraftReport(
        findings=[
            DraftFinding(
                path="app/db.py",
                line=3,
                layer="data",
                symbol=symbol,
                mechanism="The pool is smaller than the worker count.",
                severity=Severity.HIGH,
                remediation="Raise it.",
                arithmetic="",
                prediction=None,
            )
        ]
    )


def _memo(tmp_path: Path) -> Memo:
    return Memo(tmp_path / "cache")


def test_an_unchanged_file_is_served_from_the_memo(tmp_path: Path) -> None:
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    hit = memo.recall("source", "data", "python", "prompt")

    assert hit is not None
    assert hit.findings[0].symbol == "engine"


def test_changed_source_misses(tmp_path: Path) -> None:
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    assert memo.recall("source edited", "data", "python", "prompt") is None


def test_a_different_specialist_misses(tmp_path: Path) -> None:
    """One file read for two concerns is two questions."""
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    assert memo.recall("source", "network", "python", "prompt") is None


def test_a_changed_prompt_misses(tmp_path: Path) -> None:
    """The prompt is the question. A new question cannot reuse an old answer."""
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    assert memo.recall("source", "data", "python", "prompt, revised") is None


def test_a_memo_survives_a_new_process(tmp_path: Path) -> None:
    Memo(tmp_path / "cache").remember("source", "data", "python", "prompt", _draft("engine"))

    hit = Memo(tmp_path / "cache").recall("source", "data", "python", "prompt")

    assert hit is not None


def test_an_unreadable_entry_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    """A truncated cache file must cost one call, not the run."""
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))
    for path in (tmp_path / "cache").glob("*.json"):
        path.write_text("{ this is not json")

    assert memo.recall("source", "data", "python", "prompt") is None
    assert memo.hits == 0, "a corrupt entry counted as a hit as well as a miss"
    assert memo.misses == 1


def test_a_disabled_memo_never_hits(tmp_path: Path) -> None:
    """`--no-cache` has to mean it, or a stale answer is unfalsifiable."""
    memo = Memo(tmp_path / "cache", enabled=False)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    assert memo.recall("source", "data", "python", "prompt") is None


def test_the_memo_counts_what_it_saved(tmp_path: Path) -> None:
    """A cache nobody can audit is a cache nobody should trust."""
    memo = _memo(tmp_path)
    memo.remember("source", "data", "python", "prompt", _draft("engine"))

    memo.recall("source", "data", "python", "prompt")
    memo.recall("other", "data", "python", "prompt")

    assert memo.hits == 1
    assert memo.misses == 1
