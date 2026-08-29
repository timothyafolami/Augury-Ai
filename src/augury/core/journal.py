"""What happened, per project, across runs.

The memo remembers findings per file and cannot say a run *started*. A review
interrupted at module 90 of 167 therefore leaves its work behind and no account
of itself: the next person sees a warm cache and no reason for it.

This records a run before any work begins and closes it at the end. An entry
with no ending is an interrupted run, which is the fact worth keeping -- the
alternative is inferring it from the shape of a cache, and silent state that
has to be inferred is the thing this project exists to complain about.

Append-only JSONL. A run that dies mid-write costs its own line and nothing
else, which is why history is read line by line and a bad one is skipped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Run(BaseModel):
    """A review, as it is about to start."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    model: str = ""
    scope: str = ""
    modules: int = 0


class Entry(BaseModel):
    """A run, as the journal remembers it."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    model: str = ""
    scope: str = ""
    modules: int = 0
    started_at: str = ""
    finished_at: str = ""
    read: int = 0
    findings: int = 0
    usd: float = 0.0
    report: str = ""

    @property
    def interrupted(self) -> bool:
        """Started and never closed. The fact a cache alone cannot carry."""
        return not self.finished_at

    def summary(self) -> str:
        if self.interrupted:
            return (
                f"{self.started_at}  interrupted after {self.read} of {self.modules} "
                f"modules, ${self.usd:.4f} spent"
            )
        return (
            f"{self.started_at}  read {self.read} of {self.modules} modules, "
            f"{self.findings} findings, ${self.usd:.4f}"
            + (f", {self.report}" if self.report else "")
        )


class Journal:
    """One project's run history."""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "runs.jsonl"

    def begin(self, run: Run) -> None:
        """Record the run before it does anything.

        Before, not after: a run recorded on completion is a run that never
        admits to having been interrupted.
        """
        self._append(
            {
                "event": "begin",
                "run_id": run.run_id,
                "model": run.model,
                "scope": run.scope,
                "modules": run.modules,
                "started_at": _now(),
            }
        )

    def finish(self, run_id: str, *, read: int, findings: int, usd: float, report: str) -> None:
        self._append(
            {
                "event": "finish",
                "run_id": run_id,
                "finished_at": _now(),
                "read": read,
                "findings": findings,
                "usd": usd,
                "report": report,
            }
        )

    def history(self) -> list[Entry]:
        """Every run, newest first, folded from the events."""
        runs: dict[str, dict[str, object]] = {}
        order: list[str] = []
        for record in self._records():
            run_id = str(record.get("run_id") or "")
            if not run_id:
                continue
            if record.get("event") == "begin":
                runs[run_id] = {k: v for k, v in record.items() if k != "event"}
                order.append(run_id)
            elif run_id in runs:
                runs[run_id].update({k: v for k, v in record.items() if k != "event"})

        entries = [Entry.model_validate(runs[run_id]) for run_id in order if run_id in runs]
        return list(reversed(entries))

    # -- storage -----------------------------------------------------------

    def _records(self) -> list[dict[str, object]]:
        if not self._path.is_file():
            return []
        found: list[dict[str, object]] = []
        for line in self._path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError:
                # One bad append costs its own line, not the history.
                continue
            if isinstance(loaded, dict):
                found.append(loaded)
        return found

    def _append(self, record: dict[str, object]) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError:
            return


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
