"""The interface shows the run, not an animation of a run.

Every step the agents take is already recorded -- Trajectory writes one line
per deterministic step and one per model call, because "a summary is exactly
what a reader cannot check". The interface subscribes to that same record as
it is written, so what a viewer watches is the run itself.

Nothing here is simulated. If the pipeline stops emitting, the screen stops
moving, which is the honest behaviour.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from augury.server.live import LiveTrajectory, Stage, Watchers


async def test_a_subscriber_receives_what_the_run_records(tmp_path: Path) -> None:
    watchers = Watchers()
    trail = LiveTrajectory(tmp_path / "t.jsonl", watchers=watchers)
    seen = watchers.subscribe()

    trail.record(agent="surveyor", action="read", detail={"services": 8})

    event = await asyncio.wait_for(seen.get(), timeout=1.0)
    assert event["agent"] == "surveyor"
    assert event["detail"]["services"] == 8


async def test_the_record_on_disk_is_still_written(tmp_path: Path) -> None:
    """The trajectory is the evidence handed to a judge. Watching is extra."""
    path = tmp_path / "t.jsonl"
    trail = LiveTrajectory(path, watchers=Watchers())

    trail.record(agent="triage", action="routed", detail={"to": ["data"]})

    assert "triage" in path.read_text(encoding="utf-8")


async def test_two_viewers_both_see_every_step(tmp_path: Path) -> None:
    watchers = Watchers()
    trail = LiveTrajectory(tmp_path / "t.jsonl", watchers=watchers)
    first, second = watchers.subscribe(), watchers.subscribe()

    trail.record(agent="scheduler", action="chose", detail={"path": "a.py"})

    assert (await asyncio.wait_for(first.get(), 1.0))["agent"] == "scheduler"
    assert (await asyncio.wait_for(second.get(), 1.0))["agent"] == "scheduler"


async def test_a_viewer_that_leaves_does_not_stop_the_run(tmp_path: Path) -> None:
    """A closed browser tab must not raise inside the pipeline."""
    watchers = Watchers()
    trail = LiveTrajectory(tmp_path / "t.jsonl", watchers=watchers)
    seen = watchers.subscribe()
    watchers.unsubscribe(seen)

    trail.record(agent="analyst", action="found", detail={})  # must not raise


async def test_a_slow_viewer_is_dropped_rather_than_blocking_the_review() -> None:
    """A tab left open on a phone must not make the review wait for it.

    The queue is bounded and the oldest event is discarded, because a review
    that stalls behind a websocket is a review that costs money to sit still.
    """
    watchers = Watchers(depth=2)
    seen = watchers.subscribe()

    for index in range(10):
        watchers.publish({"n": index})

    assert seen.qsize() <= 2


def test_the_stages_are_the_ones_the_pipeline_actually_has() -> None:
    """The interface must not invent a phase the code does not run."""
    assert [stage.key for stage in Stage.all()] == [
        "survey",
        "map",
        "schema",
        "specialists",
        "report",
    ]


def test_every_stage_says_whether_it_costs_a_model_call() -> None:
    """Five of the seven stages consult no model, and that is the argument."""
    free = {stage.key for stage in Stage.all() if not stage.uses_model}

    assert free == {"survey", "map", "schema", "report"}


async def test_a_viewer_arriving_late_still_sees_what_it_missed(tmp_path: Path) -> None:
    """The review starts on POST and the browser subscribes after it.

    Everything published in that gap -- which model was chosen, the survey, the
    map -- was going to nobody, so the interface opened with an empty header and
    a pipeline that appeared to begin at whatever stage it happened to catch.
    """
    watchers = Watchers()
    watchers.publish({"kind": "model", "model": "openai/gpt-oss-120b"})
    watchers.publish({"kind": "stage", "stage": "survey", "state": "done"})

    arriving = watchers.subscribe()

    assert arriving.qsize() == 2
    assert (await asyncio.wait_for(arriving.get(), 1.0))["kind"] == "model"


async def test_the_replay_is_bounded_so_a_long_run_does_not_grow_forever() -> None:
    watchers = Watchers(remembers=4)

    for index in range(50):
        watchers.publish({"n": index})

    assert watchers.subscribe().qsize() == 4


async def test_a_late_viewer_sees_the_most_recent_work_not_the_oldest() -> None:
    """Truncating the front is what makes a reconnect useful mid-review."""
    watchers = Watchers(remembers=2)
    for index in range(5):
        watchers.publish({"n": index})

    arriving = watchers.subscribe()

    assert (await asyncio.wait_for(arriving.get(), 1.0))["n"] == 3
