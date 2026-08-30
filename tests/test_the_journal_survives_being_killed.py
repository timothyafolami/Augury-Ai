"""A run killed mid-write erased itself and the next complete run.

`_append` writes `json.dumps(record) + "\\n"` through a buffered handle, so a
process killed between the write and the flush leaves a line with no newline.
The next append is concatenated onto it and both records become one malformed
line -- so the interrupted run vanishes, which journal.py calls "the fact
worth keeping", and it takes an innocent completed run with it.

The module docstring says "A run that dies mid-write costs its own line and
nothing else." It cost its own line and the next run's entire existence.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.journal import Journal, Run


def _run(run_id: str) -> Run:
    return Run(run_id=run_id, model="m", scope="", modules=1)


def test_an_orphaned_line_does_not_swallow_the_next_run(tmp_path: Path) -> None:
    journal = Journal(tmp_path)
    journal.begin(_run("aaaa"))
    journal.finish("aaaa", read=1, findings=0, usd=0.0, report="")

    # A SIGKILL during the flush: a line with no terminating newline.
    with (tmp_path / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"event": "begin", "run_id": "bbbb", "started_')

    journal.begin(_run("cccc"))
    journal.finish("cccc", read=1, findings=0, usd=0.0, report="")

    seen = {entry.run_id for entry in journal.history()}
    assert "cccc" in seen, "the run after the crash was swallowed by the orphaned line"
    assert "aaaa" in seen


def test_the_run_after_a_crash_is_not_reported_as_interrupted(tmp_path: Path) -> None:
    journal = Journal(tmp_path)
    with (tmp_path / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"event": "begin", "run_id": "bbbb", "started_')

    journal.begin(_run("cccc"))
    journal.finish("cccc", read=1, findings=0, usd=0.0, report="")

    entry = next(e for e in journal.history() if e.run_id == "cccc")
    assert not entry.interrupted
