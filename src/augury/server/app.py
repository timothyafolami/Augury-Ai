"""The HTTP surface: discovery, a live review, and the report it produces.

Every endpoint runs the real pipeline. Discovery is the free half -- the
Surveyor and the Cartographer cost nothing and take about a second -- so the
deployment and the module tree are on screen before any money is spent, which
is also the argument the product makes.

A running review says what it is doing in the vocabulary `server/events.py`
declares, and every number in an event was counted by the stage that fired it.
Where a stage has nothing it can honestly say it says nothing: a fabricated
number is worse on screen than a missing one, because it cannot be told apart
from the rest.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from augury.core.cartography.languages import EXTENSIONS
from augury.core.cartography.mapper import Cartographer
from augury.core.cartography.model import RepoMap
from augury.core.layers import specialists_for
from augury.core.memo import Memo
from augury.core.survey import Surveyor
from augury.server.events import Event, EventName, Events
from augury.server.live import LiveTrajectory, Stage, Watchers

# Where the server is willing to read from. A text box that accepts any path
# on the machine is a file-disclosure endpoint with a nice font, and this is
# meant to be runnable on someone else's laptop.
ALLOWED_ROOTS = tuple(
    Path(part).expanduser().resolve()
    for part in os.environ.get(
        "AUGURY_ALLOWED_ROOTS", f"{Path.cwd()}:{Path.home() / 'Downloads'}"
    ).split(":")
    if part
)

# Named in every research event, so a reader can repeat the lookup that was
# made rather than take its answer on trust.
PACKAGE_INDEX = "pypi.org"

# The other network input. Named separately because a reader weighs a fact
# looked up in an index differently from a page a search engine ranked.
SEARCH_ENGINE = "duckduckgo"

# The flags a command uses to declare how many things it will do at once. A
# ceiling stated anywhere else is not stated: a worker's concurrency lives in
# its command, and a number taken from anywhere else is a guess wearing a
# measurement's clothes.
CEILING_FLAGS = frozenset({"--concurrency", "-c", "--workers", "-w"})

# Where the stream stops. A failure ends a run as surely as a report does, and
# a viewer left holding an open connection after one is a viewer watching a
# screen that will never move again.
ENDS_A_RUN = frozenset({EventName.REVIEW_COMPLETED.value, EventName.REVIEW_FAILED.value})


class Target(BaseModel):
    """A repository to look at, and how much of it."""

    path: str = Field(min_length=1)
    scope: str = ""
    budget: float = 0.25
    prove: int = 0


@dataclass
class Run:
    """One review, and everyone watching it."""

    run_id: str
    watchers: Watchers = field(default_factory=Watchers)
    task: asyncio.Task[Any] | None = None
    report: dict[str, Any] | None = None
    failed: str = ""


def within_allowed(path: str) -> Path:
    """Resolve this path, or refuse it.

    Resolved before comparison, so `eval/../../../etc` is judged by where it
    lands rather than by how it is spelled.
    """
    candidate = (Path.cwd() / Path(path).expanduser()).resolve()
    if not any(candidate == root or root in candidate.parents for root in ALLOWED_ROOTS):
        raise HTTPException(status_code=400, detail=f"{path} is outside the allowed roots")
    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail=f"{path} is not a directory")
    return candidate


def build() -> FastAPI:
    """The application, with its routes."""
    app = FastAPI(title="Augury", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    runs: dict[str, Run] = {}

    @app.get("/api/stages")
    def stages() -> list[dict[str, Any]]:
        """The pipeline the code actually runs, so the interface cannot invent one."""
        return [
            {
                "key": stage.key,
                "title": stage.title,
                "detail": stage.detail,
                "usesModel": stage.uses_model,
            }
            for stage in Stage.all()
        ]

    @app.post("/api/discover")
    def discover(target: Target) -> dict[str, Any]:
        """The free half: the deployment, then the map. No model, no cost."""
        root = within_allowed(target.path)
        found = Surveyor(root).survey()
        entrypoints = tuple({e for service in found.services for e in service.entrypoints})
        limits = tuple(part for part in target.scope.split(",") if part.strip())
        repo = Cartographer(root, scope=limits, entrypoints=entrypoints).map()

        return {
            "root": str(root),
            "name": root.name,
            "services": [
                {
                    "name": s.name,
                    "sourceRoot": s.source_root,
                    "command": s.command,
                    "ports": list(s.ports),
                    "isEntrypoint": s.is_entrypoint,
                }
                for s in found.services
            ],
            "backing": [{"name": b.name, "kind": b.kind, "image": b.image} for b in found.backing],
            "modules": [
                {
                    "path": m.path,
                    "loc": m.loc,
                    "depth": m.depth,
                    "fanIn": m.fan_in,
                    "signals": sorted(s.value for s in m.signals),
                }
                for m in repo.modules
            ],
            "languages": languages_in(repo),
            "unreachable": list(repo.unreachable),
        }

    @app.post("/api/review")
    async def review(target: Target) -> dict[str, str]:
        """Start a real review and hand back something to watch it with."""
        root = within_allowed(target.path)
        run = Run(run_id=uuid.uuid4().hex[:12])
        runs[run.run_id] = run
        run.task = asyncio.create_task(_review(run, root, target))
        return {"runId": run.run_id, "root": str(root), "name": root.name}

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str) -> StreamingResponse:
        """Server-sent events rather than a websocket.

        The traffic is one way, and this reconnects by itself when a laptop
        lid closes in the middle of a demonstration.
        """
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        return StreamingResponse(
            _stream(run),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str) -> dict[str, Any]:
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        if run.failed:
            raise HTTPException(status_code=500, detail=run.failed)
        if run.report is None:
            raise HTTPException(status_code=409, detail="still running")
        return run.report

    return app


async def _review(run: Run, root: Path, target: Target) -> None:
    """The real pipeline, announcing each stage as it reaches it.

    Every stage here is one the CLI runs in the same order, and every event it
    fires carries what that stage measured: the languages are counted off the
    map, the services are read off the compose file, the coverage rows are
    counted against the modules that raise each concern, and the pressures
    cannot be built without the findings they were read off.
    """
    from augury.agents.augury import AuguryReviewer
    from augury.core.adapters.provider import model_from
    from augury.core.coverage import engineering_coverage
    from augury.core.forecast import forecast
    from augury.core.reference.changelog import changelog_notes
    from augury.core.reference.registry import Registry
    from augury.core.reference.requirements import requirements_of
    from augury.core.reference.staleness import dependency_audit
    from augury.core.scheduling import Budget
    from augury.core.schema.checks import schema_findings
    from augury.core.schema.model import SchemaFinding
    from augury.core.schema.reader import read_migrations
    from augury.core.settings import load_settings

    events = Events()

    def say(event: Event) -> None:
        run.watchers.publish(event.as_json())

    try:
        settings = load_settings()
        # Built before the run announces itself, so the model named is the one
        # that will answer rather than the one the configuration asked for.
        model = model_from(settings)
        say(
            events.review_started(
                root=str(root), name=root.name, scope=target.scope, model=model.model_id
            )
        )

        say(events.scout_started())
        found = Surveyor(root).survey()
        for service in found.services:
            say(
                events.service_detected(
                    service=service.name,
                    source_root=service.source_root,
                    command=service.command,
                    capacity=capacity_of(service.command),
                )
            )
        entrypoints = tuple({e for service in found.services for e in service.entrypoints})

        limits = tuple(part for part in target.scope.split(",") if part.strip())
        repo = Cartographer(root, scope=limits, entrypoints=entrypoints).map()
        say(
            events.structure_discovered(
                modules=len(repo.modules),
                reachable=len([m for m in repo.modules if m.depth is not None]),
                unreachable=list(repo.unreachable),
            )
        )
        for language, modules in languages_in(repo).items():
            say(events.language_detected(language=language, modules=modules))
        tiers = request_path(repo)
        if tiers:
            # Omitted rather than emptied when no entrypoint is declared. There
            # is no request path to draw, and one layer holding everything
            # would be a drawing rather than a measurement.
            say(events.model_built(layers=tiers))

        bases = [root / part for part in limits] or [root]
        schema = tuple(f for base in bases for f in schema_findings(read_migrations(base)))

        # Announced as the registry announces them rather than counted off the
        # declared packages: a cached answer is not a second lookup, and a
        # package the index never answered for is not a package with nothing
        # wrong. Those two are opposite facts and read identically in silence.
        registry = Registry(watching=lambda step: _research(step, events, say))
        dependencies: list[SchemaFinding] = []
        for base in bases:
            audit = dependency_audit(requirements_of(base), registry)
            dependencies.extend(audit.findings)

        # Where to read about each major-version gap. This is the other half
        # of the reviewer's network work and the half a reader most wants to
        # see: asking the index what version is current is a fact lookup, and
        # asking a search engine where a changelog is, is the reviewer going
        # and finding something. Best effort, and announced either way, since
        # search is the first thing to fail offline and its absence costs the
        # report a section rather than the run.
        reading: dict[str, list[str]] = {}
        for stale in dependencies:
            if stale.rule != "dependency-major-versions-behind":
                continue
            package = stale.detail.split("`")[1] if "`" in stale.detail else ""
            facts = registry.facts_for(package) if package else None
            if not package or facts is None:
                continue
            say(events.research_started(subject=f"{package} changelog", source=SEARCH_ENGINE))
            notes = changelog_notes(
                package, requirements_of(bases[0]).get(package, ""), facts.latest
            )
            say(events.research_finished(subject=f"{package} changelog", found=bool(notes)))
            if notes:
                reading[package] = [note.url for note in notes[:3]]

        for deterministic in (*schema, *dependencies):
            say(events.finding_detected(finding=_finding(deterministic)))

        narration = _Narration(
            Path(".augury-runs") / f"{run.run_id}.jsonl",
            watchers=run.watchers,
            events=events,
            say=say,
            allowed=_allowed(repo),
        )
        memo = _memo_for(root, model_id=model.model_id)
        reviewer = AuguryReviewer(
            model,
            budget=Budget(usd=target.budget) if target.budget else Budget(),
            trajectory=narration,
            memo=memo,
        )
        result = await reviewer.review(repo, root)

        # Read off the store rather than accumulated at the call site, so two
        # watchers joining at different moments are told the same number.
        say(events.context_updated(what="memo hits", count=memo.hits))
        say(events.context_updated(what="memo misses", count=memo.misses))

        for finding in result.findings:
            # Announced from the finished report rather than as each specialist
            # speaks. Severity is capped against reachability and repeats are
            # collapsed afterwards, so a finding announced live is one the
            # report may go on to withdraw.
            say(events.finding_detected(finding=_finding(finding)))

        engineering = (
            engineering_coverage(repo, result.coverage, result.findings, routed=narration.routed)
            if result.coverage is not None
            else None
        )
        if engineering is not None:
            say(
                events.coverage_computed(
                    layers=[row.model_dump(mode="json") for row in engineering.layers]
                )
            )

        pressures = forecast(result.findings)
        # Fired even when it is empty. No findings group into no pressures,
        # which reads as silence, and silence is the honest output -- but an
        # interface still waiting for the event cannot tell that from a stage
        # that never ran.
        say(
            events.prediction_generated(
                items=[pressure.model_dump(mode="json") for pressure in pressures]
            )
        )

        run.report = {
            "name": root.name,
            "usd": round(result.usd, 5),
            "seconds": round(result.seconds, 1),
            "modelId": result.model_id,
            "coverage": result.coverage.model_dump() if result.coverage else None,
            "findings": [_finding(f) for f in result.findings],
            "dropped": [
                {"symbol": d.symbol, "path": d.path, "reason": d.reason} for d in result.dropped
            ],
            "reading": reading,
            "schema": [_finding(f) for f in schema],
            "dependencies": [_finding(f) for f in dependencies],
            "forecast": [pressure.model_dump(mode="json") for pressure in pressures],
        }
        if engineering is not None:
            # Absent rather than empty when the scheduler recorded no coverage.
            # Eight rows of zero over zero drawn under a heading nobody looked
            # at is the one shape of this display that actively misleads.
            run.report["engineering"] = engineering.model_dump(mode="json")
        say(events.review_completed(report=run.report))
    except Exception as error:  # a demo must say what broke, not stop moving
        run.failed = str(error)
        say(events.review_failed(detail=str(error)[:400]))


class _Narration(LiveTrajectory):
    """The run's own record, said again in the vocabulary the interface reads.

    The record still goes out unchanged, because it is what a sceptical viewer
    checks the pretty view against. What is added is the same steps under the
    names the interface groups by, read off the record rather than announced
    beside it: an event fired here cannot claim work the trajectory does not
    show, which is what makes the waterfall evidence rather than decoration.

    It also keeps which specialists triage chose for which module. That is the
    difference between a coverage row that counts and one that is an upper
    bound, and the trajectory is the only place it is written down.
    """

    def __init__(
        self,
        path: Path,
        *,
        watchers: Watchers,
        events: Events,
        say: Callable[[Event], None],
        allowed: Mapping[str, tuple[str, ...]],
    ) -> None:
        super().__init__(path, watchers=watchers)
        self._events = events
        self._say = say
        self._allowed = allowed
        self.routed: dict[str, list[str]] = {}

    def _write(self, step: dict[str, Any]) -> None:
        super()._write(step)
        agent = str(step.get("agent", ""))
        role, _, subject = agent.partition(":")

        if agent == "triage":
            # Triage was skipped: one specialist was allowed, so there was
            # nothing to narrow, and the record says which one and why.
            detail = _mapping(step.get("detail"))
            self._chose(
                str(detail.get("path", "")),
                _named(detail.get("specialists")),
                why=str(detail.get("why", "")),
            )
        elif role == "triage" and subject:
            answer = _mapping(step.get("response"))
            self._chose(
                subject, _named(answer.get("specialists")), why=str(answer.get("reasoning", ""))
            )
        elif role == "analyst" and subject and step.get("action") == "model_call":
            found = _mapping(step.get("response")).get("findings")
            self._say(
                self._events.agent_finished(
                    agent=agent, findings=len(found) if isinstance(found, list) else 0
                )
            )

    def _chose(self, module: str, named: Sequence[str], *, why: str) -> None:
        """Which specialists were asked about this module, and what sent them.

        Narrowed to what the map allows, which is the same filter triage
        applies to the model's answer: a specialist the model invented bought
        no call, so it must not appear to have read anything.
        """
        wanted = set(named)
        chosen = [layer for layer in self._allowed.get(module, ()) if layer in wanted]
        if not chosen:
            return
        self.routed[module] = chosen
        if why:
            self._say(self._events.agent_handoff(from_agent="triage", to_agent="analyst", why=why))
        for layer in chosen:
            self._say(
                self._events.agent_started(agent=f"analyst:{layer}", layer=layer, module=module)
            )


def capacity_of(command: str) -> int | None:
    """How many jobs this command declares it will run at once, or None.

    None is not one. A command that states no ceiling has an unknown one, and
    the difference between unknown and one is the difference between a worker
    that keeps up and a worker that is the queue.
    """
    tokens = command.split()
    for index, token in enumerate(tokens):
        flag, _, attached = token.partition("=")
        if flag not in CEILING_FLAGS:
            continue
        stated = attached or (tokens[index + 1] if index + 1 < len(tokens) else "")
        # A flag whose value is not a number declares no ceiling either.
        # Taking the next token regardless once reported a worker count of
        # `auto`, which is a word the interface then drew a bar for.
        if stated.isdigit() and int(stated) > 0:
            return int(stated)
    return None


def languages_in(repo: RepoMap) -> dict[str, int]:
    """How many modules of each language the map holds, commonest first.

    Counted off the map rather than off the file tree, so a language reported
    here is one the review can actually read.
    """
    counted: dict[str, int] = {}
    for module in repo.modules:
        name = EXTENSIONS[Path(module.path).suffix.lower()].value
        counted[name] = counted.get(name, 0) + 1
    return dict(sorted(counted.items(), key=lambda entry: (-entry[1], entry[0])))


def request_path(repo: RepoMap) -> list[dict[str, Any]]:
    """The modules by how far a request travels along the imports to reach them.

    Depth is the map's own measurement, so this is the system read as layers
    rather than a diagram drawn over it. A repository that declares no
    entrypoint reaches nothing from anywhere and gets no layers at all.
    """
    tiers: dict[int, list[str]] = {}
    for module in repo.modules:
        if module.depth is None:
            continue
        tiers.setdefault(module.depth, []).append(module.path)
    return [{"depth": depth, "modules": sorted(tiers[depth])} for depth in sorted(tiers)]


def _allowed(repo: RepoMap) -> dict[str, tuple[str, ...]]:
    """The specialists each module's signals justify.

    The ceiling on what triage may choose. It narrows this list and can never
    widen it, so a name outside it bought no call and read nothing.
    """
    return {
        module.path: tuple(layer.name for layer in specialists_for(module.signals))
        for module in repo.modules
    }


def _memo_for(root: Path, *, model_id: str) -> Memo:
    """Where this repository's remembered findings live.

    The same directory `augury review` keys, so a review started from the
    interface can use what one started from the terminal has already paid for.
    Outside the repository, because a reviewer that writes into the tree it is
    reading has changed the thing it is reporting on.
    """
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Memo(home / "augury" / key, model_id=model_id, enabled=True)


def _research(step: Mapping[str, object], events: Events, say: Callable[[Event], None]) -> None:
    """One lookup the registry announced, in the vocabulary the interface reads.

    Translated rather than restated. The registry knows which packages it
    actually went to the network for and what came back, including that
    nothing did, and this stage is the one place a run does work that cannot
    be checked by reading the code.
    """
    subject, source = str(step.get("subject", "")), str(step.get("source", ""))
    if not subject:
        return
    if step.get("state") == "asked" and source:
        say(events.research_started(subject=subject, source=source))
    elif step.get("state") == "answered":
        say(events.research_finished(subject=subject, found=bool(step.get("found"))))


def _mapping(value: object) -> dict[str, Any]:
    """One recorded field as a mapping, or nothing when it is not one.

    The trajectory is written by the agents and read back here, so this treats
    a step that is not shaped as expected as a step with nothing to say rather
    than as an exception inside the review.
    """
    return dict(value) if isinstance(value, dict) else {}


def _named(value: object) -> list[str]:
    """The specialist names in a recorded answer, comparably spelled."""
    if not isinstance(value, list):
        return []
    return [item.strip().lower() for item in value if isinstance(item, str)]


def _finding(item: Any) -> dict[str, Any]:
    """One finding, in the shape the interface reads."""
    prediction = getattr(item, "prediction", None)
    measurement = getattr(item, "measurement", None)
    return {
        "path": getattr(item, "path", ""),
        "line": getattr(item, "line", 0),
        "layer": getattr(item, "layer", ""),
        "symbol": getattr(item, "symbol", "") or getattr(item, "rule", ""),
        "severity": getattr(getattr(item, "severity", None), "value", "medium"),
        "mechanism": getattr(item, "mechanism", "") or getattr(item, "detail", ""),
        "remediation": getattr(item, "remediation", ""),
        "rule": getattr(item, "rule", ""),
        "prediction": (
            {
                "metric": prediction.metric,
                "comparator": prediction.comparator.value,
                "value": prediction.value,
                "upper": prediction.upper,
                "unit": prediction.unit,
                "condition": prediction.condition,
            }
            if prediction is not None
            else None
        ),
        "measurement": (
            {"value": measurement.value, "detail": measurement.detail}
            if measurement is not None
            else None
        ),
    }


async def _stream(run: Run) -> AsyncIterator[str]:
    """One watcher's view of a run, until it ends or they leave."""
    queue = run.watchers.subscribe()
    try:
        # A comment rather than a greeting event. It flushes the connection so
        # the browser knows it is open, and it is not a step of the run, which
        # is the only thing the vocabulary is allowed to describe.
        yield ": subscribed\n\n"
        while True:
            try:
                step = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                # A comment keeps proxies and browsers from closing an idle
                # connection during a long specialist call.
                yield ": still working\n\n"
                if run.task is not None and run.task.done() and run.report is not None:
                    break
                continue
            yield _sse(step)
            if step.get("event") in ENDS_A_RUN:
                break
    finally:
        run.watchers.unsubscribe(queue)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def serve_frontend(app: FastAPI, dist: Path) -> FastAPI:
    """Serve the built interface from the same process as the API.

    Only when it has been built. A missing `dist` is a development machine
    running Vite separately, not an error.
    """
    if not dist.is_dir():
        return app
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(dist / "index.html")

    return app
