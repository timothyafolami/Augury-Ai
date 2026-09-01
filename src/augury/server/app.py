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
import shutil
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from augury.cli.quiet import quiet_dependency_noise
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

# The search a reader weighs differently from an index lookup, and the one
# name here the caller has to supply: the registry announces where it asked,
# and a source named twice is a source that can disagree with itself.
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


# What a review would never read, and what a picker should therefore not show.
# These are most of a tree by count and none of it by meaning.
NEVER_REVIEWED = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".conda",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        "third_party",
        ".idea",
        ".vscode",
    }
)

# What says a directory is a repository rather than a folder above one. Any of
# them is enough: the picker is a hint, not a gate, and a repository this misses
# can still be typed in.
_A_REPOSITORY = (
    ".git",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "requirements.txt",
    "Dockerfile",
    "Makefile",
)


def _never_reviewed(child: Path) -> bool:
    return child.name in NEVER_REVIEWED


def _looks_like_a_repository(child: Path) -> bool:
    return any((child / marker).exists() for marker in _A_REPOSITORY)


def _inside_allowed(path: Path) -> bool:
    """Whether this path is one the server is willing to read from."""
    return any(path == root or root in path.parents for root in ALLOWED_ROOTS)


def recording_or_replaying() -> bool:
    """Whether every model call is served from a recording.

    Read through the settings module's own rule rather than re-implementing
    it here, so the interface and the adapter cannot disagree about which
    mode the process is in.
    """
    from augury.core.settings import replay_only

    return replay_only()


def recorded_cases() -> list[str]:
    """The repositories this checkout has recordings for, largest first.

    Read off the case directory rather than listed here, so a case added to
    the suite is offered by the interface without anyone remembering to.

    Ordered by size because the interface offers the first as its default.
    Alphabetically that was A04, three files, described in its own manifest as
    deliberately easy -- "a repository where reading everything is free" --
    which is the one case in the suite designed not to discriminate between
    the arms. Landing a first-time reviewer there shows the least of what this
    does. Ties break on the name, so the order is stable.
    """
    cases = Path(__file__).resolve().parents[3] / "eval" / "cases"
    if not cases.is_dir():
        return []
    found = [case / "repo" for case in cases.iterdir() if (case / "repo").is_dir()]
    return [str(repo) for repo in sorted(found, key=lambda r: (-_source_count(r), r.name))]


def _source_count(repo: Path) -> int:
    """Roughly how much there is to read, for ordering only.

    Counts files rather than asking the Cartographer: this runs on a page
    load, and mapping six repositories to sort a list is work nobody asked
    for. Dotted directories are skipped here for the same reason the map
    skips them.
    """
    return sum(
        1
        for path in repo.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".go", ".ts", ".tsx", ".js", ".rs", ".java", ".cpp"}
        and not any(part.startswith(".") for part in path.relative_to(repo).parts)
    )


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


class NativePickerUnavailable(RuntimeError):
    """The host cannot show a native directory chooser."""


def _picker_start(path: str) -> Path:
    """An existing, allowed directory at which to open the chooser."""
    start = (Path.cwd() / Path(path).expanduser()).resolve()
    if not _inside_allowed(start):
        raise HTTPException(status_code=400, detail=f"{path} is outside the allowed roots")
    while not start.is_dir() and start != start.parent:
        start = start.parent
    if start.is_dir() and _inside_allowed(start):
        return start
    raise HTTPException(status_code=500, detail="no allowed directory is available to open")


def native_directory(start: Path) -> Path | None:
    """Ask the host OS for a directory, returning None when the user cancels."""
    if sys.platform == "darwin":
        return _macos_directory(start)
    if sys.platform == "win32":
        return _windows_directory(start)
    if sys.platform.startswith("linux"):
        return _linux_directory(start)
    return _tkinter_directory(start)


def _macos_directory(start: Path) -> Path | None:
    escaped = str(start).replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'POSIX path of (choose folder with prompt "Choose a project directory" '
        f'default location (POSIX file "{escaped}"))'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativePickerUnavailable("the macOS folder picker could not be opened") from exc

    if result.returncode == 0:
        selected = result.stdout.strip()
        return Path(selected) if selected else None
    if "-128" in result.stderr:
        return None
    detail = (result.stderr or result.stdout).strip() or "unknown error"
    raise NativePickerUnavailable(f"the macOS folder picker failed: {detail}")


def _windows_directory(start: Path) -> Path | None:
    escaped = str(start).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$picker = New-Object System.Windows.Forms.FolderBrowserDialog; "
        '$picker.Description = "Choose a project directory"; '
        f"$picker.SelectedPath = '{escaped}'; "
        "if ($picker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::Out.Write($picker.SelectedPath) }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativePickerUnavailable("the Windows folder picker could not be opened") from exc

    if result.returncode == 0:
        selected = result.stdout.strip()
        return Path(selected) if selected else None
    detail = (result.stderr or result.stdout).strip() or "unknown error"
    raise NativePickerUnavailable(f"the Windows folder picker failed: {detail}")


def _linux_directory(start: Path) -> Path | None:
    zenity = shutil.which("zenity")
    if zenity is not None:
        return _linux_dialog(
            [zenity, "--file-selection", "--directory", "--filename", f"{start}{os.sep}"], "Zenity"
        )

    kdialog = shutil.which("kdialog")
    if kdialog is not None:
        return _linux_dialog([kdialog, "--getexistingdirectory", str(start)], "KDialog")

    return _tkinter_directory(start)


def _linux_dialog(command: list[str], name: str) -> Path | None:
    try:
        result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativePickerUnavailable(f"the {name} folder picker could not be opened") from exc

    if result.returncode == 0:
        selected = result.stdout.strip()
        return Path(selected) if selected else None
    if not result.stdout.strip() and not result.stderr.strip():
        return None
    detail = (result.stderr or result.stdout).strip()
    raise NativePickerUnavailable(f"the {name} folder picker failed: {detail}")


def _tkinter_directory(start: Path) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise NativePickerUnavailable(
            "this Python installation has no native folder picker"
        ) from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise NativePickerUnavailable(
            "the native folder picker is unavailable on this host"
        ) from exc

    try:
        root.withdraw()
        selected = filedialog.askdirectory(
            initialdir=str(start), title="Choose a project directory", mustexist=True
        )
    except tk.TclError as exc:
        raise NativePickerUnavailable(
            "the native folder picker is unavailable on this host"
        ) from exc
    finally:
        root.destroy()
    return Path(selected) if selected else None


def build() -> FastAPI:
    """The application, with its routes."""
    # Before any review runs. autogen logs the OpenAI SDK's response object,
    # whose `parsed` field is declared None and holds a parsed model, so
    # Pydantic warns nine lines per model call and buries the server log.
    quiet_dependency_noise()

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

    @app.get("/api/mode")
    def mode() -> dict[str, Any]:
        """Whether this server can call a model, and what it can review if not.

        Replay serves every call from a committed recording. Pointed at a
        recorded case that is the whole product for free; pointed at anything
        else every call misses and the interface shows a review that read
        modules, spent nothing and found nothing, with no way to tell that
        apart from a broken model. The server is the only thing that knows,
        so it says.
        """
        replaying = recording_or_replaying()
        return {
            "replay": replaying,
            # Named only when they are the answer to something. In live mode
            # every repository works and steering anyone towards these three
            # would be noise.
            "recorded": recorded_cases() if replaying else [],
        }

    @app.post("/api/browse")
    def browse(target: Target) -> dict[str, Any]:
        """The directories under this one, for choosing what to review.

        This is the one endpoint whose whole job is to disclose paths, so it
        refuses anything outside the declared roots exactly as the rest do, and
        it is resolved before it is judged.
        """
        here = within_allowed(target.path)
        directories = sorted(
            (child for child in here.iterdir() if child.is_dir() and not _never_reviewed(child)),
            key=lambda child: child.name.lower(),
        )
        parent = here.parent
        return {
            "here": str(here),
            "parent": str(parent) if _inside_allowed(parent) else "",
            "directories": [
                {
                    "name": child.name,
                    "path": str(child),
                    "looksLikeARepository": _looks_like_a_repository(child),
                }
                for child in directories
            ],
        }

    @app.post("/api/pick-directory")
    async def pick_directory(target: Target) -> dict[str, str | None]:
        """Open the host's folder chooser for the browser's primary action."""
        try:
            chosen = await asyncio.to_thread(native_directory, _picker_start(target.path))
        except NativePickerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if chosen is None:
            return {"path": None}
        return {"path": str(within_allowed(str(chosen)))}

    @app.post("/api/discover")
    async def discover(target: Target) -> dict[str, Any]:
        """The free half: the deployment, then the map. No model, no cost."""
        root = within_allowed(target.path)
        found = await asyncio.to_thread(Surveyor(root).survey)
        entrypoints = tuple({e for service in found.services for e in service.entrypoints})
        limits = tuple(part for part in target.scope.split(",") if part.strip())
        # Every synchronous pass below is handed to a thread. They read the
        # disk and the network with blocking sockets, and run straight from
        # this coroutine they stop the event loop, so the stream the interface
        # is watching goes quiet. That fails in the most misleading way
        # available: it looks exactly like a slow model.
        try:
            repo = await asyncio.to_thread(
                Cartographer(root, scope=limits, entrypoints=entrypoints).map
            )
        except ValueError as refused:
            # A scope that selects nothing is the caller's mistake, and the
            # mapper already explains it better than a message written here
            # would: it names the scope, names the root, and says why an empty
            # review is refused. Letting it escape returned 500 and the body
            # "Internal Server Error", so the interface showed a crash for a
            # field the user had mistyped.
            raise HTTPException(status_code=400, detail=str(refused)) from refused

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

    @app.get("/api/runs/{run_id}/document")
    def document(run_id: str) -> dict[str, str]:
        """The finished review as the document the CLI writes to disk.

        The same renderer, so a team reading this in a browser and a team
        reading the file are reading the same review.
        """
        run = runs.get(run_id)
        if run is None or run.report is None:
            raise HTTPException(status_code=404, detail="no finished run by that name")
        return {"markdown": run.report.get("document", "")}

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
    from augury.agents.synthesis import Synthesis
    from augury.core.adapters.provider import model_from, triage_model_from
    from augury.core.architecture import architecture
    from augury.core.artifacts import read_artifacts
    from augury.core.artifacts.checks import deployment_findings
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
        found = await asyncio.to_thread(Surveyor(root).survey)
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
        # Every synchronous pass below is handed to a thread. They read the
        # disk and the network with blocking sockets, and run straight from
        # this coroutine they stop the event loop, so the stream the interface
        # is watching goes quiet. That fails in the most misleading way
        # available: it looks exactly like a slow model.
        try:
            repo = await asyncio.to_thread(
                Cartographer(root, scope=limits, entrypoints=entrypoints).map
            )
        except ValueError as refused:
            # A scope that selects nothing is the caller's mistake, and the
            # mapper already explains it better than a message written here
            # would: it names the scope, names the root, and says why an empty
            # review is refused. Letting it escape returned 500 and the body
            # "Internal Server Error", so the interface showed a crash for a
            # field the user had mistyped.
            raise HTTPException(status_code=400, detail=str(refused)) from refused
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
        inventory = await asyncio.to_thread(read_artifacts, root)
        deployment = await asyncio.to_thread(deployment_findings, inventory.artifacts, root=root)
        schema = await asyncio.to_thread(
            lambda: tuple(f for base in bases for f in schema_findings(read_migrations(base)))
        )

        # Announced as the registry announces them rather than counted off the
        # declared packages: a cached answer is not a second lookup, and a
        # package the index never answered for is not a package with nothing
        # wrong. Those two are opposite facts and read identically in silence.
        #
        # Handed back to the loop because the audit runs on a worker thread and
        # the queues these land in belong to the loop. Publishing from the
        # thread would wake a watcher from the wrong one, and the offset stays
        # honest either way: the loop is idle while it waits on the audit.
        loop = asyncio.get_running_loop()

        def looked_up(step: dict[str, object]) -> None:
            loop.call_soon_threadsafe(_research, step, events, say)

        registry = Registry(watching=looked_up)
        dependencies: list[SchemaFinding] = []
        for base in bases:
            audit = await asyncio.to_thread(dependency_audit, requirements_of(base), registry)
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
            notes = await asyncio.to_thread(
                changelog_notes,
                package,
                requirements_of(bases[0]).get(package, ""),
                facts.latest,
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
            triage_model=triage_model_from(settings),
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

        # The service as a diagram, with the findings and the declared capacity
        # ceilings on it, so the narrowest part is visible rather than described.
        drawn = await asyncio.to_thread(architecture, found, repo, result.findings)

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

        # Last, because it reads the finished board. It is allowed to return
        # nothing: findings that do not connect produce no observation, and a
        # synthesis that always finds something is a horoscope.
        try:
            observations = await Synthesis(model).observe(report=result, survey=found)
        except Exception as refused:
            # Not a failure of the run. This is the only stage that happens
            # after the money is spent, so a complete report already exists and
            # ending the stream here would discard it over the least important
            # thing in it. Reported as context, which the interface shows and
            # nothing treats as terminal.
            say(events.context_updated(what=f"synthesis declined: {refused}"[:200], count=0))
            observations = ()

        written = await asyncio.to_thread(
            as_document,
            name=root.name,
            survey=found,
            report=result,
            schema=schema,
            dependencies=tuple(dependencies),
            deployment=deployment,
            synthesis=observations,
            modules=len(repo.modules),
            unreachable=len(repo.unreachable),
            reading=reading,
        )

        run.report = {
            "document": written,
            "architecture": drawn.model_dump(mode="json"),
            "deployment": [_finding(f) for f in deployment],
            "synthesis": [item.model_dump(mode="json") for item in observations],
            "name": root.name,
            # Where the review was pointed. The report is headed with a name,
            # and a folder called "repo" or "backend" names nothing a reader
            # can act on -- the interface climbs one level, which it cannot do
            # from a leaf on its own.
            "root": str(root),
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


def as_document(**parts: Any) -> str:
    """The report, as the document the CLI writes.

    Reused rather than reimplemented. There is one review engine, and the
    document a team acts on should not depend on which client asked for it.
    """
    from augury.core.report import write_report

    written: str = write_report(**parts)
    return written


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
                # A run that failed never produces a report, so waiting for one
                # waits for ever. The task being finished is the fact that
                # settles it either way.
                # A comment keeps proxies and browsers from closing an idle
                # connection during a long specialist call.
                yield ": still working\n\n"
                if run.task is not None and run.task.done():
                    break
                continue
            yield _sse(step)
            if step.get("event") in ENDS_A_RUN:
                break
    finally:
        run.watchers.unsubscribe(queue)


# What ends a run, in both shapes the stream has carried. The typed names
# replaced the older ones and this check was not moved, so nothing matched and
# the server never closed a connection. A finished run worked anyway because
# the browser closes its own EventSource; a failed run left both sides waiting,
# which is the state a reader with no API key landed in.
ENDS_A_RUN = frozenset({"review.completed", "review.failed"})
_OLDER_SHAPE = frozenset({"done", "failed"})


def is_terminal(step: dict[str, Any]) -> bool:
    """Whether this step means the run is over, however it was named."""
    return step.get("event") in ENDS_A_RUN or step.get("kind") in _OLDER_SHAPE


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


UNBUILT = """<!doctype html>
<title>Augury — the interface is not built</title>
<style>
  body { background:#08070c; color:#e8e6f0; font:14px/1.7 ui-monospace, monospace;
         display:grid; place-items:center; min-height:100vh; margin:0 }
  main { max-width:34rem; padding:2rem }
  h1 { font-size:1rem; letter-spacing:.3em; color:#a78bfa; font-weight:500 }
  pre { background:#14131c; padding:1rem; overflow-x:auto; border:1px solid #221f2e }
  a { color:#a78bfa }
</style>
<main>
  <h1>AUGURY</h1>
  <p>The API is running. The interface is not built, which is expected in a
     fresh clone: a build is generated, and generated files are not committed.</p>
  <pre>make web</pre>
  <p>or, without make:</p>
  <pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>
  <p>Then reload. The review engine works without any of this:
     <code>augury report --path REPO</code> writes the same document this page
     would show you.</p>
</main>
"""


def serve_frontend(app: FastAPI, dist: Path) -> FastAPI:
    """Serve the built interface from the same process as the API.

    Only when it has been built. A missing `dist` is a development machine
    running Vite separately, not an error.
    """
    if not dist.is_dir():
        # A clone has no build, because a build is generated and generated
        # files are not committed. Serving the API and a blank page at / leaves
        # a reader with no reason for it, and this is the one moment where the
        # product is invisible.
        @app.get("/", response_class=HTMLResponse)
        def unbuilt() -> str:
            return UNBUILT

        return app
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(dist / "index.html")

    return app
