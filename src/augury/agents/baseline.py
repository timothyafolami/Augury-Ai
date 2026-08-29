"""One prompt, the whole repository, no tools, one shot.

This is what a competent engineer does today: paste the code into a chat window
and ask what is wrong with it. It is the arm everything else is compared
against, so it is written to be genuinely good rather than to lose. It gets the
same instructions and the same output contract as the full pipeline, including
the demand for a falsifiable prediction.

A weak baseline would make any result meaningless.
"""

from __future__ import annotations

import time
from pathlib import Path

from augury.core.adapters.base import ChatModel
from augury.core.cartography import RepoMap
from augury.core.drafts import DraftReport, to_report
from augury.core.findings import Report
from augury.core.metrics import describe, vocabulary
from augury.core.scheduling import Coverage
from augury.prompts import render

# What one prompt can hold. The limit is the defining constraint of this arm,
# not an implementation detail, so it is stated rather than discovered.
DEFAULT_CHAR_BUDGET = 120_000

# The fence, the heading and the newlines around each file.
_BLOCK_OVERHEAD = 16


class BaselineReviewer:
    """Reviews a repository in a single model call."""

    def __init__(
        self,
        model: ChatModel,
        *,
        char_budget: int = DEFAULT_CHAR_BUDGET,
        experiments: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._budget = char_budget
        self._experiments = experiments or {}

    async def review(self, repo: RepoMap, root: Path) -> Report:
        included, skipped = self._select(repo, root)
        if not included:
            return Report(model_id=self._model.model_id, coverage=Coverage(skipped=skipped))

        started = time.monotonic()
        before = self._model.usage
        draft = await self._model.structured(
            prompt=render(
                "baseline",
                repository="\n\n".join(included),
                metrics=vocabulary(),
                experiments=describe(self._experiments),
            ),
            schema=DraftReport,
        )
        spent = self._model.usage - before

        report = to_report(
            draft,
            model_id=self._model.model_id,
            usd=spent.usd,
            seconds=time.monotonic() - started,
        )
        return report.model_copy(
            update={
                "coverage": Coverage(
                    analysed=[path for path, _ in _paths(included)],
                    skipped=skipped,
                    stopped_because="one prompt",
                )
            }
        )

    def _select(self, repo: RepoMap, root: Path) -> tuple[list[str], dict[str, str]]:
        """Fill the prompt in priority order and report what did not fit.

        Silently truncating would overstate what this arm actually saw, which
        is the one thing that would make the comparison unfair in our favour.

        The deployment configuration goes in first, ahead of any module. Half
        the defect taxonomy is a number in the source read against a number in
        the Dockerfile, and for a while this arm was asked for that arithmetic
        without being given the second number while the other arm was. That is
        not a fair comparison, and it was not even a budget constraint: this
        prompt uses about a seventh of what it is allowed.
        """
        ordered = sorted(repo.modules, key=lambda m: (-m.fan_in, -len(m.signals), m.path))
        included: list[str] = [
            f"### {name}\n```\n{text}\n```" for name, text in repo.context.items()
        ]
        skipped: dict[str, str] = {
            **{path: "unparsed" for path in repo.unparsed},
            **dict(repo.skipped),
        }
        used = sum(len(block) for block in included)

        for module in ordered:
            remaining = self._budget - used
            if remaining <= _BLOCK_OVERHEAD:
                skipped[module.path] = "did not fit in one prompt"
                continue

            text = (root / module.path).read_text(encoding="utf-8", errors="replace")
            room = remaining - _BLOCK_OVERHEAD - len(module.path)

            if len(text) > room:
                # What a person actually does when the file is too long: paste
                # what fits. Recording it keeps the arm's coverage honest.
                text = text[:room] + "\n... truncated ...\n"
                skipped[module.path] = "truncated to fit one prompt"

            block = f"### {module.path}\n```\n{text}\n```"
            included.append(block)
            used += len(block)

        return included, skipped


def _paths(blocks: list[str]) -> list[tuple[str, str]]:
    return [(block.split("\n", 1)[0].removeprefix("### "), block) for block in blocks]
