"""Not paying twice to read a file that has not changed.

A review of a real backend is 167 modules and several minutes. Run it again
after editing three files and 164 of those calls buy exactly the answer they
bought last time, at the same price, against the tokens-per-minute ceiling that
is the actual constraint on how fast this can go.

The key is the source, the specialist, the language and the prompt itself. A
changed prompt is a different question and must miss -- the same argument as
the model cassettes one layer down. A cache that answers a new question with an
old answer is worse than no cache, because nothing downstream can tell.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from augury.core.drafts import DraftReport


class Memo:
    """Findings for one file, one specialist, one prompt, kept on disk."""

    def __init__(self, directory: Path, *, model_id: str = "", enabled: bool = True) -> None:
        self._dir = Path(directory)
        # A different model is a different answerer to the same question, and
        # nothing downstream can tell: the report and the journal both take
        # the model from the adapter, so a switched model was credited with
        # findings it never saw.
        self._model_id = model_id
        self._enabled = enabled
        self.hits = 0
        self.misses = 0
        if self._enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    def recall(self, source: str, layer: str, language: str, prompt: str) -> DraftReport | None:
        """What this specialist said last time, if the question is unchanged."""
        if not self._enabled:
            return None
        path = self._path(source, layer, language, prompt)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            draft = DraftReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A truncated or half-written entry costs one call, not the run.
            self.misses += 1
            return None
        self.hits += 1
        return draft

    def remember(
        self, source: str, layer: str, language: str, prompt: str, draft: DraftReport
    ) -> None:
        if not self._enabled:
            return
        path = self._path(source, layer, language, prompt)
        # Written beside and moved, so an interrupted run leaves no half file
        # for the next one to parse.
        temporary = path.with_suffix(".partial")
        try:
            temporary.write_text(draft.model_dump_json(), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return

    def _path(self, source: str, layer: str, language: str, prompt: str) -> Path:
        digest = hashlib.sha256(
            json.dumps([self._model_id, source, layer, language, prompt]).encode("utf-8")
        ).hexdigest()
        return self._dir / f"{digest}.json"
