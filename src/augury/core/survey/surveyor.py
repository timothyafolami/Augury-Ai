"""Turning a compose file into a scope for the review.

Everything here is deterministic. The compose file is a declaration, not a
guess, and a model asked to infer the same facts would occasionally infer them
wrongly at a cost per file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from augury.core.survey.model import BackingService, Service, Survey

COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

# What an image is, by the name people actually use for it. A specialist that
# knows it is talking to a cache asks different questions than one talking to a
# relational database, and the image tag is the cheapest place to learn which.
IMAGE_KINDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("postgres", "postgis", "timescale", "mysql", "mariadb", "cockroach"), "database"),
    (("redis", "valkey", "keydb"), "cache or queue"),
    (("rabbitmq", "kafka", "nats", "activemq", "pulsar"), "message broker"),
    (("qdrant", "weaviate", "milvus", "chroma", "pinecone"), "vector store"),
    (("elasticsearch", "opensearch", "meilisearch", "typesense"), "search index"),
    (("minio", "localstack", "azurite"), "object store"),
    (("mongo",), "document store"),
    (("clickhouse", "druid"), "analytics store"),
    (("nginx", "traefik", "haproxy", "envoy", "caddy"), "reverse proxy"),
    (("prometheus", "grafana", "jaeger", "loki", "tempo", "otel"), "observability"),
)


class Surveyor:
    """Reads a repository's deployment declaration."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def survey(self) -> Survey:
        compose = self._compose()
        if compose is None:
            return Survey()

        services: list[Service] = []
        backing: list[BackingService] = []
        for name, spec in (compose.get("services") or {}).items():
            if not isinstance(spec, dict):
                continue
            root = self._source_root(spec)
            if root is None:
                backing.append(self._backing(name, spec))
            else:
                services.append(self._service(name, spec, root))

        roots: list[str] = []
        for service in services:
            if service.source_root and service.source_root not in roots:
                roots.append(service.source_root)

        return Survey(
            services=tuple(services),
            backing=tuple(backing),
            source_roots=tuple(roots),
            external=self._external(compose),
        )

    # -- reading -----------------------------------------------------------

    def _compose(self) -> dict[str, Any] | None:
        for name in COMPOSE_FILES:
            path = self._root / name
            if not path.is_file():
                continue
            try:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            except yaml.YAMLError:
                # A compose file we cannot parse is not a reason to refuse the
                # review; it is a reason to review without a scope.
                return None
            if isinstance(loaded, dict):
                return loaded
        return None

    def _source_root(self, spec: dict[str, Any]) -> str | None:
        """The directory a service is built from, or None if it is an image."""
        build = spec.get("build")
        if isinstance(build, str):
            return self._normalise(build)
        if isinstance(build, dict):
            context = build.get("context")
            if isinstance(context, str):
                return self._normalise(context)
            return ""
        return None

    @staticmethod
    def _normalise(context: str) -> str:
        cleaned = context.strip().removeprefix("./").rstrip("/")
        return "" if cleaned in {".", ""} else cleaned

    def _service(self, name: str, spec: dict[str, Any], root: str) -> Service:
        return Service(
            name=name,
            source_root=root,
            command=_as_command(spec.get("command")),
            ports=tuple(str(p) for p in _as_list(spec.get("ports"))),
            depends_on=tuple(_depends_on(spec.get("depends_on"))),
            environment=_as_environment(spec.get("environment")),
        )

    def _backing(self, name: str, spec: dict[str, Any]) -> BackingService:
        image = str(spec.get("image") or "")
        haystack = f"{name} {image}".lower()
        kind = next(
            (kind for names, kind in IMAGE_KINDS if any(n in haystack for n in names)),
            "unknown",
        )
        return BackingService(name=name, image=image, kind=kind)

    @staticmethod
    def _external(compose: dict[str, Any]) -> tuple[str, ...]:
        """Volumes and networks the file declares as living outside it."""
        found: list[str] = []
        for section in ("volumes", "networks"):
            for name, spec in (compose.get(section) or {}).items():
                if isinstance(spec, dict) and spec.get("external"):
                    found.append(f"{section[:-1]}:{name}")
        return tuple(found)


# -- compose's several spellings of the same thing -------------------------


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _as_command(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(part) for part in value) if isinstance(value, list) else str(value)


def _depends_on(value: Any) -> list[str]:
    """`depends_on` is a list in the short form and a mapping in the long one."""
    if isinstance(value, dict):
        return [str(name) for name in value]
    return [str(name) for name in _as_list(value)]


def _as_environment(value: Any) -> dict[str, str]:
    """`environment` is a mapping in one form and `KEY=value` strings in another."""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    pairs: dict[str, str] = {}
    for item in _as_list(value):
        key, _, val = str(item).partition("=")
        if key:
            pairs[key] = val
    return pairs
