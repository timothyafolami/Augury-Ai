"""`augury report` must be able to write down what its agents did.

`augury review` takes `--trajectory` and `augury report` did not, which meant
the three agents that only run in the report path -- the Surveyor reading the
deployment, the synthesis pass that turns findings into a document, and the
forecast -- could not be recorded at all. The submission asks for a
representative trajectory for every agent used, and for those three there was
no command that would produce one.

This is a gap in the product before it is a gap in the paperwork: a reviewer
who wants to know why the report said something has the findings and not the
steps that produced them.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from augury.cli import main


def test_report_accepts_a_trajectory_path() -> None:
    """The same option name `review` uses, because two names for one idea is
    how a reader ends up believing only one command can record."""
    signature = inspect.signature(main.report)

    assert "trajectory" in signature.parameters


def test_review_and_report_agree_on_the_option() -> None:
    """Whatever the help text says, it should say it identically in both."""
    on_review = inspect.signature(main.review).parameters["trajectory"]
    on_report = inspect.signature(main.report).parameters["trajectory"]

    assert on_review.default.help == on_report.default.help


def test_the_reviewer_is_given_the_recording(tmp_path: Path) -> None:
    """Accepting the flag and dropping it is the failure this guards.

    `--prove` was accepted and ignored once already on this command, and every
    verdict printed "untested" while the run reported success.
    """
    source = inspect.getsource(main.report)

    assert "trajectory=recording" in source, (
        "report() takes the flag but never hands it to the reviewer"
    )


def test_a_recorded_report_names_its_agents(tmp_path: Path) -> None:
    """The file has to be readable as steps, not just exist."""
    from augury.core.trajectory import Trajectory

    written = tmp_path / "run.jsonl"
    recording = Trajectory(written)
    recording.record(agent="surveyor", action="read", detail={"services": 1})
    recording.record(agent="synthesis", action="model_call", detail={"sections": 4})

    steps = [json.loads(line) for line in written.read_text().splitlines()]

    assert [s["agent"] for s in steps] == ["surveyor", "synthesis"]


@pytest.mark.parametrize("command", ["review", "report"])
def test_both_commands_document_the_option_the_same_way(command: str) -> None:
    option = inspect.signature(getattr(main, command)).parameters["trajectory"].default

    assert "JSONL" in option.help


def test_the_deterministic_passes_are_recorded_too() -> None:
    """The Surveyor and the schema/deployment/dependency passes consult no
    model, which is exactly why they were invisible: a trajectory built only
    from model calls omits the free half of the pipeline, and the free half is
    what decides which modules the paid half ever sees."""
    source = inspect.getsource(main.report)

    for agent in ('agent="surveyor"', 'agent="artifacts"'):
        assert agent in source, f"report() never records {agent}"
