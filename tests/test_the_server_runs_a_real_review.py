"""The interface's API. Nothing here is a mock of a review.

The discovery endpoint runs the real Surveyor and Cartographer, which cost
nothing and take a second, so the tree and the services are on screen before
any money is spent. The review endpoint runs the real pipeline and streams the
real trajectory.

The events a run publishes are checked against the run that published them
rather than against a fixture. A test asserting that `language.detected` says
python is a test that passes when the server invents the word; asserting that
it says what the map holds is a test that fails when it does.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from augury.agents.triage import TriageDecision
from augury.core.adapters.base import Completion, Usage
from augury.core.cartography.mapper import Cartographer
from augury.core.cartography.model import ModuleNode, RepoMap
from augury.core.coverage import engineering_coverage
from augury.core.drafts import DraftFinding, DraftReport
from augury.core.findings import Severity
from augury.core.forecast import Mechanism, Pressure
from augury.core.reference.registry import Registry
from augury.core.scheduling import Coverage
from augury.core.survey import Surveyor
from augury.server.app import Run, Target, _review, build, capacity_of, request_path
from augury.server.events import VOCABULARY, EventName
from augury.server.live import Watchers

# The one case in the repository that declares a deployment, so it is the one
# a survey has anything to say about.
CASE = "eval/cases/B01-orders-service/repo"


def _client() -> TestClient:
    return TestClient(build())


def test_discovery_reports_the_services_the_compose_file_declares() -> None:
    """The free half of the review, and the part that opens the demo."""
    with _client() as client:
        answer = client.post("/api/discover", json={"path": CASE})

    assert answer.status_code == 200
    assert "services" in answer.json()


def test_discovery_reports_the_module_tree() -> None:
    with _client() as client:
        found = client.post("/api/discover", json={"path": CASE}).json()

    assert found["modules"], "no modules mapped"
    assert any(m["path"].endswith(".py") for m in found["modules"])


def test_discovery_reports_which_languages_were_found() -> None:
    with _client() as client:
        found = client.post("/api/discover", json={"path": CASE}).json()

    assert found["languages"], "no languages reported"


def test_a_path_outside_the_allowed_roots_is_refused() -> None:
    """The server reads whatever it is pointed at, so it is pointed narrowly.

    A demo that will run on someone else's machine must not accept
    `/etc` or `~/.ssh` from a text box.
    """
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "/etc"})

    assert answer.status_code == 400


def test_a_path_that_climbs_out_with_dots_is_refused() -> None:
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "eval/../../../etc"})

    assert answer.status_code == 400


def test_the_stages_endpoint_names_the_pipeline_the_code_runs() -> None:
    with _client() as client:
        stages = client.get("/api/stages").json()

    assert [s["key"] for s in stages] == ["survey", "map", "schema", "specialists", "report"]


def test_a_missing_path_says_so_rather_than_failing_opaquely() -> None:
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "eval/cases/nope"})

    assert answer.status_code == 404


def test_starting_a_review_returns_something_to_watch() -> None:
    with _client() as client:
        started = client.post("/api/review", json={"path": CASE, "budget": 0.02})

    assert started.status_code == 200
    assert started.json()["runId"]


def test_a_run_that_was_never_started_has_no_stream() -> None:
    with _client() as client:
        answer = client.get("/api/runs/nope/events")

    assert answer.status_code == 404


def test_a_run_that_was_never_started_has_no_report() -> None:
    with _client() as client:
        answer = client.get("/api/runs/nope/report")

    assert answer.status_code == 404


def test_the_stream_is_server_sent_events() -> None:
    """Chosen over websockets because the traffic is one-way and this
    reconnects by itself when a laptop lid closes mid-demo."""
    with _client() as client:
        run_id = client.post("/api/review", json={"path": CASE, "budget": 0.02}).json()["runId"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
            assert stream.headers["content-type"].startswith("text/event-stream")


def test_a_review_of_a_refused_path_is_refused_before_it_starts() -> None:
    with _client() as client:
        answer = client.post("/api/review", json={"path": "/etc"})

    assert answer.status_code == 400


def test_the_built_interface_is_served_when_it_has_been_built(tmp_path: Path) -> None:
    """One process serves both in production, so a demo needs one command."""
    from augury.server.app import serve_frontend

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>augury</title>", encoding="utf-8")

    with TestClient(serve_frontend(build(), dist)) as client:
        assert client.get("/").status_code == 200


def test_a_missing_build_is_a_development_machine_not_an_error() -> None:
    """Vite runs separately in development; the API must still start."""
    from augury.server.app import serve_frontend

    app = serve_frontend(build(), Path("/nonexistent/dist"))

    with TestClient(app) as client:
        assert client.get("/api/stages").status_code == 200


def test_the_report_carries_engineering_coverage_per_layer() -> None:
    """The interface draws a bar per specialist, and a bar with no basis
    beside it looks exactly like a measurement."""
    repo = Cartographer(Path(CASE)).map()
    computed = engineering_coverage(repo, Coverage(analysed=[]), [])

    assert computed.layers, "no layers reported"
    assert all(row.basis for row in computed.layers), "a row with no stated basis"


def test_a_layer_nothing_touches_reports_no_share_rather_than_a_full_bar() -> None:
    """We looked at all zero of them is not a reassuring fact."""
    repo = Cartographer(Path(CASE)).map()
    computed = engineering_coverage(repo, Coverage(analysed=[]), [])

    empty = [row for row in computed.layers if row.appears_in == 0]
    assert all(row.share is None for row in empty)


def test_a_forecast_item_can_never_be_built_without_its_evidence() -> None:
    """The one property that keeps a forecast from becoming a horoscope."""
    with pytest.raises(ValidationError):
        Pressure(mechanism=next(iter(Mechanism)), evidence=(), rule="because")


# -- one real run, watched ---------------------------------------------------

# What each specialist says when it is asked, keyed by the concern it owns.
# Two sentences rather than one because a forecast groups by mechanism, and a
# single sentence would prove only that the grouping compiles.
SAID = {
    "data": "the handler issues one query per line item, an n+1 in a loop",
    "network": "the client is built with no timeout, so the pool saturates under load",
}

# Where the analyst prompt names the file and the concern. Read rather than
# counted, so the answers depend on the question and two runs of one repository
# are told the same things.
_PATH = re.compile(r"^Path: (.+)$", re.MULTILINE)
_CONCERN = re.compile(r"knowledge of (\w+)")

# A queue deep enough that nothing this run says is dropped before a test can
# read it. The live one is deliberately shallow, because a review that waits
# for a browser is a review paying a model to sit still.
KEEPS_EVERYTHING = 100_000


class _OfflineRegistry(Registry):
    """The real registry, asked of an index that never answers.

    Subclassed rather than replaced so the announcements under test are the
    ones the registry itself makes; only the transport is stubbed, because a
    review has to work on a train and so does this suite. It also puts the
    honest half of `research.finished` under test: could not be reached,
    rather than checked and current.
    """

    def __init__(self, *, watching: Callable[[dict[str, object]], None] | None = None) -> None:
        super().__init__(fetch=lambda _: None, watching=watching)


class _Specialists:
    """A model that answers from the prompt rather than from a provider.

    Every answer is derived from the question it was asked, so two reviews of
    one repository ask and are told exactly the same things. That is what lets
    a test compare a second review's cache hits against the first's misses.
    """

    model_id = "test-model"

    @property
    def usage(self) -> Usage:
        """Nothing was spent, and the report should say so rather than round."""
        return Usage()

    async def structured[T: BaseModel](self, *, prompt: str, schema: type[T]) -> T:
        raise AssertionError("the reviewer calls `call`, never `structured`")

    async def call[T: BaseModel](self, *, prompt: str, schema: type[T]) -> Completion:
        if schema is TriageDecision:
            return Completion(
                result=TriageDecision(
                    specialists=sorted(SAID), reasoning="the file touches both concerns"
                ),
                usage=Usage(),
            )
        return Completion(result=_draft(prompt), usage=Usage())


def _draft(prompt: str) -> DraftReport:
    """One finding about the file this prompt names, in the concern it asks for."""
    concern = _CONCERN.search(prompt)
    path = _PATH.search(prompt)
    if concern is None or path is None or concern.group(1) not in SAID:
        return DraftReport(findings=[])
    layer, where = concern.group(1), path.group(1).strip()
    return DraftReport(
        findings=[
            DraftFinding(
                path=where,
                line=1,
                layer=layer,
                symbol=f"{layer}_in_{where}",
                mechanism=SAID[layer],
                severity=Severity.MEDIUM,
                remediation="not the subject of this test",
                arithmetic="",
                prediction=None,
            )
        ]
    )


@dataclass(frozen=True)
class Reviewed:
    """One real review, and everything it said while it ran."""

    steps: list[dict[str, Any]]
    run: Run
    cache: Path

    @property
    def events(self) -> list[dict[str, Any]]:
        """The typed events, without the trajectory the run also publishes."""
        return [step for step in self.steps if "event" in step]

    def named(self, name: EventName) -> list[dict[str, Any]]:
        return [step for step in self.events if step["event"] == name.value]

    def data(self, name: EventName) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = [step["data"] for step in self.named(name)]
        return payloads

    def only(self, name: EventName) -> dict[str, Any]:
        found = self.data(name)
        assert len(found) == 1, f"{name.value} fired {len(found)} times, not once"
        return found[0]


def _reviewed(cache: Path) -> Reviewed:
    """Run the whole pipeline over a real repository, without a provider.

    The Surveyor, the Cartographer, the schema pass, the scheduler and the
    report are the real ones. The model is not, because a test that spends
    money is a test nobody runs, and the package index is not, because a review
    has to work offline and so does this suite.
    """
    run = Run(run_id="test", watchers=Watchers(depth=KEEPS_EVERYTHING, remembers=KEEPS_EVERYTHING))
    seen = run.watchers.subscribe()
    environment = {
        "XDG_CACHE_HOME": str(cache),
        # A key rather than the replay flag. The model here is already a stub,
        # so nothing was ever replayed: the flag was only a way to satisfy the
        # settings check without a key, and it made this run claim to be
        # something it is not. The memo stands down under replay -- a cache
        # above the cassettes can answer differently from the recording -- so
        # a fixture that says "replay" to mean "no key" turns the caching test
        # below into an assertion about nothing.
        "GROQ_API_KEY": "test-key-not-used-the-model-is-a-stub",
        "AUGURY_PROVIDER": "groq",
        "AUGURY_MODEL": "openai/gpt-oss-120b",
    }
    with (
        mock.patch("augury.core.adapters.provider.model_from", lambda _: _Specialists()),
        mock.patch("augury.core.reference.registry.Registry", _OfflineRegistry),
        # The reviewer holds its own registry to tell each specialist what is
        # installed, and it bound the name at import.
        mock.patch("augury.agents.augury.Registry", _OfflineRegistry),
        mock.patch.dict(os.environ, environment),
    ):
        asyncio.run(_review(run, Path(CASE), Target(path=CASE)))

    steps: list[dict[str, Any]] = []
    while not seen.empty():
        steps.append(seen.get_nowait())
    return Reviewed(steps=steps, run=run, cache=cache)


@pytest.fixture(scope="module")
def reviewed(tmp_path_factory: pytest.TempPathFactory) -> Reviewed:
    """One review, shared by every test that asks a question about it.

    Module-scoped because this runs the real pipeline over a real repository,
    and paying for that once per assertion makes a suite nobody runs.
    """
    return _reviewed(tmp_path_factory.mktemp("cache"))


def test_the_run_finishes_rather_than_reporting_what_broke(reviewed: Reviewed) -> None:
    """Every other test here reads a run that got to the end, so this says so
    first: a failure otherwise arrives as eleven confusing assertions."""
    assert reviewed.run.failed == ""
    assert reviewed.run.report is not None


def test_the_run_says_only_words_the_interface_knows(reviewed: Reviewed) -> None:
    """A name the vocabulary does not hold is a bar that never appears."""
    said = {step["event"] for step in reviewed.events}

    assert said, "the run published no events at all"
    assert said <= VOCABULARY


def test_nothing_the_run_publishes_is_an_ad_hoc_dict(reviewed: Reviewed) -> None:
    """Two shapes go down this wire: the trajectory the reviewer writes anyway,
    and events from the vocabulary. A third is one the interface reads by
    guessing at its keys, which is how a stage stops lighting up in silence."""
    stray = [step for step in reviewed.steps if "event" not in step and "agent" not in step]

    assert stray == []


def test_the_events_are_numbered_from_one_without_gaps(reviewed: Reviewed) -> None:
    """The interface orders by this, so a gap is a step it thinks it missed."""
    numbers = [step["seq"] for step in reviewed.events]

    assert numbers == list(range(1, len(numbers) + 1))


def test_every_event_carries_how_far_into_the_run_it_happened(reviewed: Reviewed) -> None:
    offsets = [step["offsetMs"] for step in reviewed.events]

    assert offsets == sorted(offsets)
    assert offsets[0] >= 0


def test_the_run_names_the_repository_and_the_model_that_answered(
    reviewed: Reviewed,
) -> None:
    started = reviewed.only(EventName.REVIEW_STARTED)

    assert started["name"] == Path(CASE).name
    assert started["root"].endswith(CASE)
    # The model that actually answered, taken from the adapter rather than
    # from configuration: those two disagree the moment a fallback fires.
    assert started["model"] == _Specialists.model_id


def test_the_languages_are_counted_off_the_map(reviewed: Reviewed) -> None:
    """Counted rather than sampled: the languages sum to the modules mapped."""
    detected = reviewed.data(EventName.LANGUAGE_DETECTED)
    counted = {row["language"]: row["modules"] for row in detected}
    mapped = Cartographer(Path(CASE)).map()

    assert counted == {"python": len(mapped.modules)}
    assert sum(counted.values()) == reviewed.only(EventName.STRUCTURE_DISCOVERED)["modules"]


def test_the_services_are_the_ones_the_compose_file_declares(reviewed: Reviewed) -> None:
    """The database is an image rather than something built from this source,
    so it is not a service this repository can be reviewed for."""
    detected = {row["service"]: row for row in reviewed.data(EventName.SERVICE_DETECTED)}
    declared = {service.name for service in Surveyor(Path(CASE)).survey().services}

    assert set(detected) == declared
    assert detected


def test_a_service_declaring_no_ceiling_reports_none_rather_than_one(
    reviewed: Reviewed,
) -> None:
    """A worker's concurrency lives in its command. This compose file gives no
    command, so the number is unknown, and one is a plausible invention."""
    for row in reviewed.data(EventName.SERVICE_DETECTED):
        assert row["capacity"] is None


@pytest.mark.parametrize(
    ("command", "capacity"),
    [
        ("celery -A src.tasks.celery_app worker --concurrency 4", 4),
        ("celery -A app worker --concurrency=16", 16),
        ("gunicorn -w 8 app.main:app", 8),
        ("uvicorn app.main:app --workers 2 --host 0.0.0.0", 2),
        ("uvicorn app.main:app", None),
        ("", None),
        # A flag whose value is not a number declares no ceiling either. Taking
        # the next token regardless once reported a worker count of `auto`.
        ("celery -A app worker --concurrency auto", None),
    ],
)
def test_a_ceiling_is_read_off_the_command_or_not_read_at_all(
    command: str, capacity: int | None
) -> None:
    assert capacity_of(command) == capacity


def test_the_structure_is_the_map_the_cartographer_drew(reviewed: Reviewed) -> None:
    """Including what no entrypoint reaches, listed rather than counted: eleven
    files nothing imports is a claim a reader is entitled to check."""
    found = reviewed.only(EventName.STRUCTURE_DISCOVERED)
    mapped = _the_same_map()

    assert found["modules"] == len(mapped.modules)
    assert found["reachable"] == len([m for m in mapped.modules if m.depth is not None])
    assert found["unreachable"] == list(mapped.unreachable)


def test_the_request_path_is_the_depth_the_map_measured() -> None:
    """The system model is the map read as layers, entrypoint first, rather
    than a diagram drawn over it."""
    repo = RepoMap(
        root=".",
        modules=[
            ModuleNode(path="app/main.py", loc=10, depth=0),
            ModuleNode(path="app/api.py", loc=10, depth=1),
            ModuleNode(path="app/db.py", loc=10, depth=1),
        ],
    )

    assert request_path(repo) == [
        {"depth": 0, "modules": ["app/main.py"]},
        {"depth": 1, "modules": ["app/api.py", "app/db.py"]},
    ]


def test_a_repository_declaring_no_entrypoint_has_no_request_path() -> None:
    """Nothing reaches anything, so a single layer called everything would be
    a drawing rather than a measurement."""
    repo = RepoMap(root=".", modules=[ModuleNode(path="app/main.py", loc=10)])

    assert request_path(repo) == []


def test_a_package_the_index_never_answered_about_is_reported_as_unknown(
    reviewed: Reviewed,
) -> None:
    """Checked and current, and could not be reached, are opposite facts about
    one package, and the interface may not show either as the other."""
    started = {row["subject"] for row in reviewed.data(EventName.RESEARCH_STARTED)}
    finished = reviewed.data(EventName.RESEARCH_FINISHED)

    assert "fastapi" in started, "the requirements file was never looked up"
    assert {row["subject"] for row in finished} == started
    assert all(row["found"] is False for row in finished)


def test_the_specialists_that_read_a_module_are_the_ones_triage_chose(
    reviewed: Reviewed,
) -> None:
    started = reviewed.data(EventName.AGENT_STARTED)

    assert started, "no specialist was announced"
    assert {row["layer"] for row in started} <= set(SAID)
    assert all(row["module"] for row in started)


def test_a_specialist_that_finished_reports_the_findings_it_returned(
    reviewed: Reviewed,
) -> None:
    """Counted off the answer the trajectory recorded, so an event cannot
    claim work the record does not show."""
    finished = reviewed.data(EventName.AGENT_FINISHED)

    assert finished, "no specialist was announced as finished"
    assert all(row["findings"] >= 0 for row in finished)
    assert sum(row["findings"] for row in finished) > 0


def test_the_handoff_says_what_made_the_work_pass(reviewed: Reviewed) -> None:
    handoffs = reviewed.data(EventName.AGENT_HANDOFF)

    assert handoffs, "nothing was handed to a specialist"
    assert all(row["from"] == "triage" for row in handoffs)
    assert all(row["why"] for row in handoffs)


def test_every_finding_in_the_report_reached_the_stream(reviewed: Reviewed) -> None:
    """The report is authoritative: severity is capped and repeats are
    collapsed after the specialists have spoken, so what is announced is what
    survived that rather than what was first said."""
    assert reviewed.run.report is not None
    published = reviewed.data(EventName.FINDING_DETECTED)
    report = reviewed.run.report
    expected = len(report["findings"]) + len(report["schema"]) + len(report["dependencies"])

    assert len(published) == expected
    assert expected > 0


def test_the_coverage_event_carries_the_rows_the_report_carries(
    reviewed: Reviewed,
) -> None:
    assert reviewed.run.report is not None
    announced = reviewed.only(EventName.COVERAGE_COMPUTED)["layers"]

    assert announced == reviewed.run.report["engineering"]["layers"]
    assert announced, "no specialist was reported on"


def test_every_coverage_row_says_the_reviewed_count_was_measured(
    reviewed: Reviewed,
) -> None:
    """The server knows which specialists triage actually chose, because the
    trajectory records it. That turns the share from an upper bound into a
    count, and the row has to say which of the two it is."""
    rows = reviewed.only(EventName.COVERAGE_COMPUTED)["layers"]

    assert all(row["basis"] == "routed" for row in rows)


def test_a_layer_no_specialist_was_asked_about_reviewed_nothing(
    reviewed: Reviewed,
) -> None:
    """The distinction the basis field exists for. Triage chose two concerns,
    so the other six read nothing, however many modules raised them."""
    rows = reviewed.only(EventName.COVERAGE_COMPUTED)["layers"]
    unasked = [row for row in rows if row["layer"] not in SAID]

    assert unasked
    assert all(row["reviewed"] == [] for row in unasked)
    assert any(row["occurrences"] for row in unasked), "no unasked layer was even raised"


def test_the_forecast_reaches_the_stream_and_the_report(reviewed: Reviewed) -> None:
    assert reviewed.run.report is not None
    items = reviewed.only(EventName.PREDICTION_GENERATED)["items"]

    assert items == reviewed.run.report["forecast"]
    assert {item["mechanism"] for item in items} == {
        "query amplification",
        "connection pool exhaustion",
    }


def test_every_pressure_carries_the_findings_it_was_read_off(reviewed: Reviewed) -> None:
    """A bar next to a mechanism name looks exactly like a measurement unless
    something travelling with it says otherwise."""
    for item in reviewed.only(EventName.PREDICTION_GENERATED)["items"]:
        assert item["evidence"], "a pressure with no evidence"
        assert item["independent_findings"] == len(item["evidence"])
        assert item["derivation"]
        assert item["rule"]


def test_the_cache_counts_are_the_ones_the_store_kept(reviewed: Reviewed) -> None:
    """A second review of an unchanged repository asks the same questions, so
    the hits it reports are exactly the misses the first one paid for. Counted
    by the store rather than accumulated at the call site, which is the only
    way two watchers are told the same number."""
    first = {row["what"]: row["count"] for row in reviewed.data(EventName.CONTEXT_UPDATED)}

    again = _reviewed(reviewed.cache)
    second = {row["what"]: row["count"] for row in again.data(EventName.CONTEXT_UPDATED)}

    assert first["memo misses"] > 0
    assert first["memo hits"] == 0
    assert second["memo hits"] == first["memo misses"]
    assert second["memo misses"] == 0


def test_the_run_ends_by_handing_over_the_report_it_produced(
    reviewed: Reviewed,
) -> None:
    completed = reviewed.only(EventName.REVIEW_COMPLETED)

    assert completed["report"] == reviewed.run.report
    assert reviewed.events[-1]["event"] == EventName.REVIEW_COMPLETED.value


def test_the_report_endpoint_serves_what_the_run_computed(reviewed: Reviewed) -> None:
    """The payload the interface reads, rather than the object it came from."""
    assert reviewed.run.report is not None
    report = reviewed.run.report

    assert report["engineering"]["modules"] > 0
    assert report["forecast"]
    assert report["modelId"] == _Specialists.model_id


def test_a_run_that_breaks_says_so_in_the_same_vocabulary() -> None:
    """A demonstration must say what broke rather than stop moving."""
    run = Run(run_id="broken", watchers=Watchers())
    seen = run.watchers.subscribe()

    with mock.patch("augury.core.adapters.provider.model_from", side_effect=RuntimeError("no key")):
        asyncio.run(_review(run, Path(CASE), Target(path=CASE)))

    steps: list[dict[str, Any]] = []
    while not seen.empty():
        steps.append(seen.get_nowait())

    assert steps[-1]["event"] == EventName.REVIEW_FAILED.value
    assert "no key" in steps[-1]["data"]["detail"]
    assert run.failed


def _the_same_map() -> RepoMap:
    """The map the server drew, drawn again the way the server draws it.

    Through the survey, because the entrypoints a compose file declares are
    what makes a module reachable, and a map built without them reports every
    depth as None.
    """
    found = Surveyor(Path(CASE)).survey()
    entrypoints = tuple({e for service in found.services for e in service.entrypoints})
    return Cartographer(Path(CASE), entrypoints=entrypoints).map()


def test_browsing_lists_the_directories_under_a_path() -> None:
    """A text field asks someone to remember a path. A picker shows them."""
    with _client() as client:
        seen = client.post("/api/browse", json={"path": "eval/cases"}).json()

    assert any(entry["name"] == "B01-orders-service" for entry in seen["directories"])


def test_browsing_refuses_a_path_outside_the_allowed_roots() -> None:
    """The picker is the one endpoint whose whole job is to disclose paths."""
    with _client() as client:
        answer = client.post("/api/browse", json={"path": "/etc"})

    assert answer.status_code == 400


def test_browsing_says_which_directories_look_like_a_repository() -> None:
    """So the picker can lead somewhere useful rather than everywhere.

    A case directory holds a repository beside its experiments and its fixed
    copy, so the marker belongs on `repo` and not on the case above it.
    """
    with _client() as client:
        seen = client.post("/api/browse", json={"path": "eval/cases/B01-orders-service"}).json()

    marked = {entry["name"]: entry["looksLikeARepository"] for entry in seen["directories"]}
    assert marked.get("repo") is True
    assert marked.get("experiments") is False


def test_browsing_hides_the_directories_a_review_would_never_read() -> None:
    """node_modules and .venv are most of a tree and none of a repository."""
    with _client() as client:
        seen = client.post("/api/browse", json={"path": "."}).json()

    names = {entry["name"] for entry in seen["directories"]}
    assert ".venv" not in names
    assert ".git" not in names


def test_browsing_offers_the_way_back_up() -> None:
    with _client() as client:
        seen = client.post("/api/browse", json={"path": "eval/cases"}).json()

    assert seen["parent"], "no way to go up from a subdirectory"


def test_the_report_is_served_as_the_document_the_cli_writes() -> None:
    """One engine. The document a team acts on is the same one either way."""
    from augury.core.findings import Report
    from augury.core.survey.model import Survey
    from augury.server.app import as_document

    written = as_document(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=Report(findings=(), model_id="m", usd=0.0, seconds=1.0),
        schema=(),
        dependencies=(),
        modules=10,
        unreachable=0,
        reading={},
    )

    assert written.startswith("# svc")


def test_an_unbuilt_interface_says_how_to_build_it(tmp_path: Path) -> None:
    """A clone has no web/dist, because a build is generated and not committed.

    Serving the API and nothing at / leaves a reader with a blank page and no
    reason for it. This is the one moment where the product is invisible, so
    it says what to run.
    """
    from augury.server.app import serve_frontend

    with TestClient(serve_frontend(build(), tmp_path / "nowhere")) as client:
        answer = client.get("/")

    assert answer.status_code == 200
    assert "npm" in answer.text


def test_a_built_interface_is_served_instead_of_the_instructions(tmp_path: Path) -> None:
    from augury.server.app import serve_frontend

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>augury</title>", encoding="utf-8")

    with TestClient(serve_frontend(build(), dist)) as client:
        assert "augury" in client.get("/").text
