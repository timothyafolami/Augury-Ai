"""Mapping imported names to the lab layer that owns the concern.

Deliberately conservative. A signal here means "a specialist from this layer
has something to look at", and a false signal costs a real model call, so the
table only contains names that genuinely imply the concern.
"""

from __future__ import annotations

from augury.core.cartography.model import Signal

# Top-level module name -> the concerns importing it implies.
IMPORT_SIGNALS: dict[str, frozenset[Signal]] = {
    # 01-machine
    "threading": frozenset({Signal.CONCURRENCY}),
    "multiprocessing": frozenset({Signal.CONCURRENCY}),
    "concurrent": frozenset({Signal.CONCURRENCY}),
    "asyncio": frozenset({Signal.CONCURRENCY}),
    # 02-network
    "httpx": frozenset({Signal.NETWORK}),
    "requests": frozenset({Signal.NETWORK}),
    "aiohttp": frozenset({Signal.NETWORK}),
    "urllib3": frozenset({Signal.NETWORK}),
    "socket": frozenset({Signal.NETWORK}),
    # 03-data
    "sqlalchemy": frozenset({Signal.DATA}),
    "psycopg": frozenset({Signal.DATA}),
    "asyncpg": frozenset({Signal.DATA}),
    "sqlite3": frozenset({Signal.DATA}),
    "sqlmodel": frozenset({Signal.DATA}),
    # 04-distributed / 05-failure
    "celery": frozenset({Signal.DISTRIBUTED, Signal.FAILURE}),
    "redis": frozenset({Signal.DISTRIBUTED}),
    "kombu": frozenset({Signal.DISTRIBUTED}),
    "tenacity": frozenset({Signal.FAILURE}),
    "backoff": frozenset({Signal.FAILURE}),
    # 06-observability
    "logging": frozenset({Signal.OBSERVABILITY}),
    "structlog": frozenset({Signal.OBSERVABILITY}),
    "opentelemetry": frozenset({Signal.OBSERVABILITY}),
    "prometheus_client": frozenset({Signal.OBSERVABILITY}),
    # 07-security
    "jwt": frozenset({Signal.SECURITY}),
    "hashlib": frozenset({Signal.SECURITY}),
    "hmac": frozenset({Signal.SECURITY}),
    "secrets": frozenset({Signal.SECURITY}),
    "subprocess": frozenset({Signal.SECURITY}),
    # entrypoints
    "fastapi": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
    "flask": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
    "django": frozenset({Signal.ENTRYPOINT}),
    "starlette": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
}


def signals_for_import(top_level: str) -> frozenset[Signal]:
    return IMPORT_SIGNALS.get(top_level, frozenset())
