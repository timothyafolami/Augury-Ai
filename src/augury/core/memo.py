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
from augury.core.settings import recording, replay_only


class Memo:
    """Findings for one file, one specialist, one prompt, kept on disk."""

    def __init__(self, directory: Path, *, model_id: str = "", enabled: bool = True) -> None:
        self._dir = Path(directory)
        # A recording that a memo answered is a recording that was never
        # written. The cassette set then replays on the machine whose cache
        # happened to be warm and on no other, which is the same as not
        # having one. The saving is worth less than a set that travels.
        #
        # Replay is the same argument from the other end. It exists to
        # reproduce one recorded run, and a cache above the cassettes can hold
        # a different answer to the same question -- filled by a live run on
        # another day -- and being the outer layer it wins. Measured: the same
        # review of the same repository against the same cassettes gave 16
        # findings and a 259-line document with a cold memo, and 10 findings
        # and 207 lines with a warm one. The published numbers held only on a
        # machine that had never run it before.
        #
        # The memo is an optimisation for live runs, and only for those.
        if enabled and (recording() or replay_only()):
            enabled = False
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
