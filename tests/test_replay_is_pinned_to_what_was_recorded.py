"""A recording is of one model. Replaying it under another cannot work.

The cassette key includes the model id, correctly -- two models given one
prompt are two different runs. But `make eval-replay` took the model from the
ambient environment, so changing AUGURY_PROVIDER in .env made every published
number irreproducible, and the error blamed missing cassettes:

    CassetteMiss: no recording for this call ... Run `make eval-live` to
    record, or check the cassettes are committed.

Both suggestions were wrong. The cassettes were committed and complete; they
were for a different model, and nothing said so.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.adapters.cassette import RECORDED_WITH, CassetteMiss, miss_report


def test_the_message_names_the_model_that_was_asked_for() -> None:
    said = miss_report(model_id="deepseek/deepseek-v4-flash", directory=Path("/c"), recorded=())

    assert "deepseek-v4-flash" in said


def test_the_message_names_the_model_the_recordings_are_of() -> None:
    """The one fact that turns a confusing failure into an obvious one."""
    said = miss_report(
        model_id="deepseek/deepseek-v4-flash",
        directory=Path("/c"),
        recorded=("groq/openai/gpt-oss-120b",),
    )

    assert "openai/gpt-oss-120b" in said


def test_a_mismatch_does_not_advise_re_recording() -> None:
    """Re-recording would overwrite a complete set to fix a wrong question."""
    said = miss_report(
        model_id="deepseek/deepseek-v4-flash",
        directory=Path("/c"),
        recorded=("groq/openai/gpt-oss-120b",),
    )

    assert "eval-live" not in said


def test_a_genuine_gap_under_the_right_model_still_says_to_record() -> None:
    said = miss_report(
        model_id="groq/openai/gpt-oss-120b",
        directory=Path("/c"),
        recorded=("groq/openai/gpt-oss-120b",),
    )

    assert "eval-live" in said


def test_the_makefile_replays_the_model_the_cassettes_hold() -> None:
    """Otherwise a judge who copies .env.example reproduces nothing."""
    makefile = Path("Makefile").read_text(encoding="utf-8")
    target = makefile.split("eval-replay:", 1)[1].split("\n\n", 1)[0]

    assert "AUGURY_PROVIDER=" in target
    assert "AUGURY_MODEL=" in target


def test_the_pinned_model_is_the_one_actually_recorded() -> None:
    """A pin that names the wrong model is worse than no pin."""
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert RECORDED_WITH in makefile


def test_a_cassette_miss_is_still_an_error_not_a_shrug() -> None:
    assert issubclass(CassetteMiss, Exception)
