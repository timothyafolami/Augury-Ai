"""The service as a diagram, drawn from what was read.

Every node and every edge here traces back to something already established: a
service the compose file declares, a directory the map holds, a backing service
something imports. Nothing is inferred from the shape of the name, because a
diagram is the one artefact a reader believes without checking, and one with a
node nobody can trace back is worth less than nothing.

The overlay is the point. A node carries the capacity ceiling its deployment
declares and the findings that landed inside it, so the narrowest part of the
service is visible rather than described.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from augury.core.cartography import RepoMap
from augury.core.survey.model import Survey

# A diagram stops being one somewhere around here. A repository with 1,100
# modules is a hairball at one node per file, so code is grouped by the
# directory that owns it and the widest groups are kept.
MOST_GROUPS = 14

# Flags that cap throughput. They appear in the deployment and in no source
# file, which is the whole reason the survey runs before the code is read.
CEILINGS = (
    "--concurrency",
    "--workers",
    "--pool",
    "--prefetch-multiplier",
    "--max-tasks-per-child",
    "--threads",
)


class Node(BaseModel):
    """One box: a service, a group of modules, or a store."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    kind: str = Field(description="service, code or store")
    detail: str = ""
    ceiling: str = Field(
        default="", description="The capacity flag its deployment declares, if any"
    )
    modules: int = Field(default=0, ge=0)
    findings: int = Field(default=0, ge=0)
    depth: int | None = Field(default=None, description="Hops from an entrypoint, for the layout")


class Edge(BaseModel):
    """One line, and why it is there."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    why: str = ""


class Architecture(BaseModel):
    """What was drawn, and what it was drawn from."""

    model_config = ConfigDict(frozen=True)

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    basis: str = Field(
        default="",
        description="The sentence saying where this came from, carried in the payload "
        "because a diagram reads as authoritative unless something says otherwise.",
    )


def architecture(survey: Survey, repo: RepoMap, findings: Sequence[Any]) -> Architecture:
    """Draw the service from the deployment, the map and the findings."""
    if not survey.services and not repo.modules:
        return Architecture()

    per_path = _findings_by_path(findings)
    nodes: list[Node] = []
    edges: list[Edge] = []

    for service in survey.services:
        nodes.append(
            Node(
                id=f"svc:{service.name}",
                label=service.name,
                kind="service",
                detail=service.source_root or ".",
                ceiling=_ceiling(service.command),
                depth=0,
            )
        )

    for backing in survey.backing:
        nodes.append(
            Node(
                id=f"store:{backing.name}",
                label=backing.name,
                kind="store",
                detail=backing.kind,
                depth=3,
            )
        )

    groups = _groups(repo, per_path)
    nodes.extend(groups)

    # An entrypoint reaches the code. Drawn from the service that takes traffic
    # where the compose file names one, and from every service otherwise.
    serving = [s for s in survey.services if s.is_entrypoint] or list(survey.services)
    shallowest = sorted(groups, key=lambda node: (node.depth or 99, -node.modules))[:4]
    for service in serving[:2]:
        for group in shallowest:
            edges.append(
                Edge(
                    source=f"svc:{service.name}",
                    target=group.id,
                    why="a request reaches this package",
                )
            )

    # The code reaches the stores. Drawn only where something in the group
    # actually imports the client library, never from the name of the store.
    for group in groups:
        for backing in survey.backing:
            if _touches(repo, group, backing.name):
                edges.append(
                    Edge(
                        source=group.id,
                        target=f"store:{backing.name}",
                        why=f"imports a {backing.name} client",
                    )
                )

    return Architecture(
        nodes=tuple(nodes),
        edges=tuple(edges),
        basis=(
            f"{len(survey.services)} services from the compose file, "
            f"{len(groups)} packages from the module map, "
            f"{len(survey.backing)} backing services. Edges are drawn where an "
            "import was found, never from a name."
        ),
    )


def _groups(repo: RepoMap, per_path: dict[str, int]) -> list[Node]:
    """Modules, gathered into the package that owns them."""
    gathered: dict[str, list[Any]] = {}
    for module in repo.modules:
        parts = Path(module.path).parts
        # Two segments: one is the repository, and three is a file list.
        key = "/".join(parts[: min(2, max(len(parts) - 1, 1))])
        gathered.setdefault(key, []).append(module)

    nodes: list[Node] = []
    for key, held in gathered.items():
        depths = [m.depth for m in held if m.depth is not None]
        nodes.append(
            Node(
                id=f"code:{key}",
                label=key.split("/")[-1] or key,
                kind="code",
                detail=key,
                modules=len(held),
                findings=sum(per_path.get(m.path, 0) for m in held),
                depth=min(depths) + 1 if depths else None,
            )
        )

    nodes.sort(key=lambda node: (-node.findings, -node.modules))
    return nodes[:MOST_GROUPS]


def _findings_by_path(findings: Sequence[Any]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for finding in findings:
        path = str(getattr(finding, "path", "") or "")
        if path:
            counted[path] = counted.get(path, 0) + 1
    return counted


def _touches(repo: RepoMap, group: Node, backing: str) -> bool:
    """Whether anything in this package imports a client for that store.

    The store's own name is the weakest possible signal and is used only
    alongside the client libraries that actually talk to it, so a module named
    `redis_config` does not draw an edge it has not earned.
    """
    wanted = _CLIENTS.get(backing, (backing,))
    for module in repo.modules:
        if not module.path.startswith(group.detail):
            continue
        if any(name in wanted for name in module.external):
            return True
    return False


# What a service is actually reached through. Derived from the client library
# rather than from the service name, because the name proves nothing.
_CLIENTS = {
    "redis": ("redis", "aioredis", "redis.asyncio", "ioredis", "go-redis"),
    "postgres": ("psycopg", "psycopg2", "asyncpg", "sqlalchemy", "pg", "pgx"),
    "qdrant": ("qdrant_client", "qdrant"),
    "mysql": ("pymysql", "aiomysql", "mysql"),
    "mongo": ("pymongo", "motor", "mongodb"),
    "rabbitmq": ("pika", "aio_pika", "kombu"),
    "kafka": ("kafka", "aiokafka", "confluent_kafka"),
}


def _ceiling(command: str) -> str:
    """The capacity flags this command declares, as written."""
    words = command.split()
    kept = [
        word if "=" in word else f"{word} {words[index + 1]}"
        for index, word in enumerate(words)
        if word.split("=", 1)[0] in CEILINGS and (index + 1 < len(words) or "=" in word)
    ]
    return " ".join(kept)
