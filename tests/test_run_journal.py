"""What happened, per project, across runs.

The memo remembers findings per file. It cannot say a run *started*, so a
review interrupted at module 90 of 167 leaves its work behind and no account of
itself: the next person sees a warm cache and no reason for it.

A journal records the run before any work begins and closes it at the end. An
entry with no ending is an interrupted run, and saying so is the whole point --
the alternative is inferring it from a cache, which is exactly the kind of
silent state this project exists to complain about.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.journal import Journal, Run


def _journal(tmp_path: Path) -> Journal:
    return Journal(tmp_path / "journal")


def test_a_run_is_recorded_before_any_work_happens(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    journal.begin(Run(run_id="r1", model="deepseek-v4-flash", scope="backend", modules=167))

    entries = journal.history()
    assert len(entries) == 1
    assert entries[0].finished_at == ""


def test_a_finished_run_records_what_it_cost_and_covered(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.begin(Run(run_id="r1", model="m", scope="backend", modules=167))

    journal.finish("r1", read=167, findings=41, usd=1.87, report="review.md")

    entry = journal.history()[0]
    assert entry.read == 167
    assert entry.usd == 1.87
    assert entry.report == "review.md"
    assert entry.finished_at


def test_an_unfinished_run_reads_as_interrupted(tmp_path: Path) -> None:
    """The thing the memo alone cannot tell you."""
    journal = _journal(tmp_path)
    journal.begin(Run(run_id="r1", model="m", scope="backend", modules=167))

    entry = journal.history()[0]

    assert entry.interrupted is True
    assert "interrupted" in entry.summary().lower()


def test_a_finished_run_does_not_read_as_interrupted(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.begin(Run(run_id="r1", model="m", scope="backend", modules=167))
    journal.finish("r1", read=167, findings=41, usd=1.87, report="review.md")

    assert journal.history()[0].interrupted is False


def test_history_is_newest_first(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    for identifier in ("r1", "r2", "r3"):
        journal.begin(Run(run_id=identifier, model="m", scope="backend", modules=1))

    assert [entry.run_id for entry in journal.history()] == ["r3", "r2", "r1"]


def test_a_journal_survives_a_new_process(tmp_path: Path) -> None:
    Journal(tmp_path / "journal").begin(Run(run_id="r1", model="m", scope="backend", modules=5))

    assert len(Journal(tmp_path / "journal").history()) == 1


def test_a_corrupt_line_does_not_lose_the_rest(tmp_path: Path) -> None:
    """One bad append must not make the history unreadable."""
    journal = _journal(tmp_path)
    journal.begin(Run(run_id="r1", model="m", scope="backend", modules=5))
    (tmp_path / "journal" / "runs.jsonl").open("a").write("{ not json\n")
    journal.begin(Run(run_id="r2", model="m", scope="backend", modules=5))

    assert {entry.run_id for entry in journal.history()} == {"r1", "r2"}


def test_finishing_a_run_that_was_never_begun_is_ignored(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    journal.finish("never-started", read=1, findings=0, usd=0.0, report="")

    assert journal.history() == []
