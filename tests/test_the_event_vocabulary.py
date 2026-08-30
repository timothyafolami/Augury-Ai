"""The interface and the pipeline have to agree on what happened.

Ad hoc dicts agree right up until someone renames a key. Then the screen stops
showing a stage, nothing raises, and the demonstration is a review that looks
like it skipped a step. So there is one constructor per event, the name is
spelled once inside it, and the full set is asserted here: a renamed event
fails this test rather than quietly stopping reaching the interface.

The clock is passed in. A waterfall needs real offsets, and a test that sleeps
to get them is a test nobody runs.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from augury.server.events import VOCABULARY, Event, EventName, Events

# What the interface reads out of each event, by name. Written out rather than
# derived from the constructors, so a payload key cannot be renamed on both
# sides at once and still pass.
FIELDS: dict[str, frozenset[str]] = {
    "review.started": frozenset({"root", "name", "scope", "model"}),
    "scout.started": frozenset(),
    "language.detected": frozenset({"language", "modules"}),
    "framework.detected": frozenset({"framework", "evidence"}),
    "service.detected": frozenset({"service", "sourceRoot", "command", "capacity"}),
    "structure.discovered": frozenset({"modules", "reachable", "unreachable"}),
    "model.built": frozenset({"layers"}),
    "agent.started": frozenset({"agent", "layer", "module"}),
    "agent.handoff": frozenset({"from", "to", "why"}),
    "agent.finished": frozenset({"agent", "findings"}),
    "research.started": frozenset({"subject", "source"}),
    "research.finished": frozenset({"subject", "found"}),
    "finding.detected": frozenset({"finding"}),
    "context.updated": frozenset({"what", "count"}),
    "coverage.computed": frozenset({"layers"}),
    "prediction.generated": frozenset({"items"}),
    "review.completed": frozenset({"report"}),
    "review.failed": frozenset({"detail"}),
}


class _Clock:
    """A clock that moves only when the test moves it."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


def _one_of_each(events: Events) -> list[Event]:
    """Every event in the vocabulary, made the only way it can be made."""
    return [
        events.review_started(root="/repo", name="repo", scope="backend", model="gpt-oss-120b"),
        events.scout_started(),
        events.language_detected(language="python", modules=42),
        events.framework_detected(framework="fastapi", evidence="backend/app/main.py"),
        events.service_detected(
            service="worker",
            source_root="backend",
            command="celery -A src.tasks.celery_app worker --concurrency 4",
            capacity=4,
        ),
        events.structure_discovered(modules=42, reachable=31, unreachable=("scripts/seed.py",)),
        events.model_built(layers=({"name": "entrypoint", "modules": ["app/main.py"]},)),
        events.agent_started(agent="analyst", layer="data", module="app/orders.py"),
        events.agent_handoff(from_agent="triage", to_agent="analyst", why="data signals"),
        events.agent_finished(agent="analyst", findings=2),
        events.research_started(subject="sqlalchemy", source="pypi"),
        events.research_finished(subject="sqlalchemy", found=True),
        events.finding_detected(finding={"path": "app/orders.py", "line": 12}),
        events.context_updated(what="memo", count=7),
        events.coverage_computed(layers=({"layer": "data", "analysed": 4},)),
        events.prediction_generated(items=({"metric": "queries_per_request"},)),
        events.review_completed(report={"findings": [], "usd": 0.04}),
        events.review_failed(detail="the registry timed out"),
    ]


def test_the_vocabulary_is_exactly_the_names_the_interface_expects() -> None:
    """Spelled out, so a rename has to be made here too and cannot be silent."""
    assert frozenset(FIELDS) == VOCABULARY


def test_every_name_in_the_vocabulary_has_a_constructor() -> None:
    """A name nothing can construct is a stage the interface waits for forever."""
    made = {event.name for event in _one_of_each(Events())}

    assert made == VOCABULARY


def test_no_two_constructors_emit_the_same_name() -> None:
    """Two constructors sharing a name is one event the interface never sees."""
    made = [event.name for event in _one_of_each(Events())]

    assert len(made) == len(set(made))


def test_every_name_is_dotted() -> None:
    """`subject.verb`, so the interface can group by subject without a table."""
    for name in VOCABULARY:
        subject, _, verb = name.partition(".")
        assert subject and verb, f"{name} is not a dotted name"


def test_each_event_carries_the_fields_the_interface_reads() -> None:
    for event in _one_of_each(Events()):
        assert frozenset(event.data) == FIELDS[event.name], (
            f"{event.name} carries {sorted(event.data)}, not {sorted(FIELDS[event.name])}"
        )


def test_the_sequence_numbers_run_from_one_without_gaps() -> None:
    """The interface orders by this, so a gap is a step it thinks it missed."""
    numbers = [event.seq for event in _one_of_each(Events())]

    assert numbers == list(range(1, len(numbers) + 1))


def test_the_offset_is_the_milliseconds_the_clock_actually_moved() -> None:
    clock = _Clock()
    events = Events(clock=clock)

    first = events.scout_started()
    clock.seconds = 1.25
    second = events.scout_started()

    assert (first.offset_ms, second.offset_ms) == (0, 1250)


def test_the_offset_is_measured_from_the_start_of_this_run_not_from_the_epoch() -> None:
    """A clock already running when the review starts must not become an offset."""
    clock = _Clock()
    clock.seconds = 9_000.0
    events = Events(clock=clock)

    assert events.scout_started().offset_ms == 0


def test_offsets_never_go_backwards_along_the_waterfall() -> None:
    clock = _Clock()
    events = Events(clock=clock)

    offsets = []
    for step in range(4):
        clock.seconds = step * 0.5
        offsets.append(events.scout_started().offset_ms)

    assert offsets == sorted(offsets)


def test_every_event_is_plain_json() -> None:
    """Server-sent events carry text. A payload needing a custom encoder is a
    payload that reaches the browser as an exception."""
    for event in _one_of_each(Events()):
        shape = event.as_json()

        assert json.loads(json.dumps(shape)) == shape


def test_the_json_carries_the_name_the_sequence_and_the_offset() -> None:
    shape = Events().scout_started().as_json()

    assert shape["event"] == "scout.started"
    assert shape["seq"] == 1
    assert shape["offsetMs"] >= 0
    assert shape["data"] == {}


def test_the_handoff_says_which_agent_it_came_from_and_which_it_went_to() -> None:
    """`from` is a reserved word, so the parameter cannot be spelled like the
    field. The field is what the interface reads, and it is checked here."""
    handoff = Events().agent_handoff(from_agent="triage", to_agent="analyst", why="data signals")

    assert handoff.data["from"] == "triage"
    assert handoff.data["to"] == "analyst"


def test_a_service_that_declares_no_ceiling_reports_none_rather_than_one() -> None:
    """A worker's concurrency lives in its command and nowhere else. Absent, it
    is unknown, and this tool does not fill unknowns in with a plausible number."""
    service = Events().service_detected(
        service="api", source_root="backend", command="uvicorn app.main:app", capacity=None
    )

    assert service.data["capacity"] is None


def test_an_event_cannot_be_edited_after_it_is_numbered() -> None:
    """The sequence number is what the interface trusts to order the waterfall."""
    event = Events().scout_started()

    with pytest.raises(FrozenInstanceError):
        event.seq = 99  # type: ignore[misc]


def test_editing_the_payload_afterwards_does_not_reach_the_stream() -> None:
    """The caller keeps its own dict. An event is what was true when it fired."""
    finding: dict[str, Any] = {"path": "app/orders.py"}
    event = Events().finding_detected(finding=finding)

    finding["path"] = "somewhere/else.py"

    assert event.data["finding"] == {"path": "app/orders.py"}


def test_the_enum_is_the_single_spelling_of_every_name() -> None:
    """One place a name is written, so a typo is a NameError rather than an
    event the interface silently never receives."""
    assert {member.value for member in EventName} == VOCABULARY
