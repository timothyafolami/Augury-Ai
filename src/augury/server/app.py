"""The HTTP surface: discovery, a live review, and the report it produces.

Every endpoint runs the real pipeline. Discovery is the free half -- the
Surveyor and the Cartographer cost nothing and take about a second -- so the
deployment and the module tree are on screen before any money is spent, which
is also the argument the product makes.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
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
from augury.core.survey import Surveyor
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

        languages: dict[str, int] = {}
        for module in repo.modules:
            name = EXTENSIONS[Path(module.path).suffix.lower()].value
            languages[name] = languages.get(name, 0) + 1

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
            "languages": languages,
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

    Every stage here is one the CLI runs in the same order. The interface
    subscribes to the trajectory the reviewer writes anyway, so what a viewer
    sees is the run rather than a narration of it.
    """
    from augury.agents.augury import AuguryReviewer, Progress
    from augury.core.adapters.provider import model_from
    from augury.core.reference.registry import Registry
    from augury.core.reference.requirements import requirements_of
    from augury.core.reference.staleness import dependency_audit
    from augury.core.scheduling import Budget
    from augury.core.schema.checks import schema_findings
    from augury.core.schema.reader import read_migrations
    from augury.core.settings import load_settings

    say = run.watchers.publish
    try:
        settings = load_settings()
        say({"kind": "model", "provider": settings.spec.provider, "model": settings.spec.model})

        say({"kind": "stage", "stage": "survey", "state": "running"})
        found = Surveyor(root).survey()
        entrypoints = tuple({e for service in found.services for e in service.entrypoints})
        say(
            {
                "kind": "stage",
                "stage": "survey",
                "state": "done",
                "detail": {
                    "services": len(found.services),
                    "backing": len(found.backing),
                    "entrypoints": len(entrypoints),
                },
            }
        )

        say({"kind": "stage", "stage": "map", "state": "running"})
        limits = tuple(part for part in target.scope.split(",") if part.strip())
        repo = Cartographer(root, scope=limits, entrypoints=entrypoints).map()
        reached = len([m for m in repo.modules if m.depth is not None])
        say(
            {
                "kind": "stage",
                "stage": "map",
                "state": "done",
                "detail": {"modules": len(repo.modules), "reachable": reached},
            }
        )

        say({"kind": "stage", "stage": "schema", "state": "running"})
        bases = [root / part for part in limits] or [root]
        schema = tuple(f for base in bases for f in schema_findings(read_migrations(base)))
        registry = Registry()
        audits = [dependency_audit(requirements_of(base), registry) for base in bases]
        dependencies = tuple(f for audit in audits for f in audit.findings)
        say(
            {
                "kind": "deterministic",
                "schema": [_finding(f) for f in schema],
                "dependencies": [_finding(f) for f in dependencies],
            }
        )
        say(
            {
                "kind": "stage",
                "stage": "schema",
                "state": "done",
                "detail": {"schema": len(schema), "dependencies": len(dependencies)},
            }
        )

        say({"kind": "stage", "stage": "specialists", "state": "running"})

        def watching(event: object) -> None:
            if isinstance(event, Progress):
                say(
                    {
                        "kind": "module",
                        "path": event.path,
                        "depth": event.depth,
                        "findings": event.findings,
                        "read": event.read,
                        "total": event.total,
                        "usd": round(event.usd, 5),
                    }
                )

        reviewer = AuguryReviewer(
            model_from(settings),
            budget=Budget(usd=target.budget) if target.budget else Budget(),
            watching=watching,
            trajectory=LiveTrajectory(
                Path(".augury-runs") / f"{run.run_id}.jsonl", watchers=run.watchers
            ),
        )
        result = await reviewer.review(repo, root)
        say({"kind": "stage", "stage": "specialists", "state": "done"})

        say({"kind": "stage", "stage": "report", "state": "running"})
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
            "schema": [_finding(f) for f in schema],
            "dependencies": [_finding(f) for f in dependencies],
        }
        say({"kind": "stage", "stage": "report", "state": "done"})
        say({"kind": "done", "report": run.report})
    except Exception as error:  # a demo must say what broke, not stop moving
        run.failed = str(error)
        say({"kind": "failed", "detail": str(error)[:400]})


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
        yield _sse({"kind": "hello", "runId": run.run_id})
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
            if step.get("kind") == "done":
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
