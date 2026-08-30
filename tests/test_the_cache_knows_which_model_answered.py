"""A different model is a different answerer to the same question.

The key was source, layer, language and prompt. Run a review with one model
and then another, and the second serves the first's findings verbatim -- while
`Report.model_id` and the journal both record the second model, because both
read it from the adapter rather than from the answer.

memo.py's own docstring states the rule this breaks: "A cache that answers a
new question with an old answer is worse than no cache, because nothing
downstream can tell."
"""

from __future__ import annotations

from pathlib import Path

from augury.core.drafts import DraftReport
from augury.core.memo import Memo


def _memo(tmp_path: Path, model: str) -> Memo:
    return Memo(tmp_path, model_id=model)


def test_a_second_model_does_not_get_the_first_model_s_answer(tmp_path: Path) -> None:
    cheap = _memo(tmp_path, "groq/openai/gpt-oss-20b")
    cheap.remember("src", "security", "python", "the prompt", DraftReport(findings=[]))

    expensive = _memo(tmp_path, "anthropic/claude-sonnet-4-5")

    assert expensive.recall("src", "security", "python", "the prompt") is None


def test_the_same_model_still_gets_its_own_answer(tmp_path: Path) -> None:
    """The cache has to keep working, or this is not a fix."""
    memo = _memo(tmp_path, "groq/openai/gpt-oss-20b")
    memo.remember("src", "security", "python", "the prompt", DraftReport(findings=[]))

    assert (
        _memo(tmp_path, "groq/openai/gpt-oss-20b").recall("src", "security", "python", "the prompt")
        is not None
    )
