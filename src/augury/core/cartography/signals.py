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
    "urllib": frozenset({Signal.NETWORK}),
    "http": frozenset({Signal.NETWORK}),
    "socket": frozenset({Signal.NETWORK}),
    "boto3": frozenset({Signal.NETWORK}),
    "botocore": frozenset({Signal.NETWORK}),
    "grpc": frozenset({Signal.NETWORK}),
    # 03-data
    "sqlalchemy": frozenset({Signal.DATA}),
    "psycopg": frozenset({Signal.DATA}),
    "psycopg2": frozenset({Signal.DATA}),
    "asyncpg": frozenset({Signal.DATA}),
    "sqlite3": frozenset({Signal.DATA}),
    "sqlmodel": frozenset({Signal.DATA}),
    "pymysql": frozenset({Signal.DATA}),
    "MySQLdb": frozenset({Signal.DATA}),
    "aiomysql": frozenset({Signal.DATA}),
    "pymongo": frozenset({Signal.DATA}),
    "motor": frozenset({Signal.DATA}),
    "peewee": frozenset({Signal.DATA}),
    "tortoise": frozenset({Signal.DATA}),
    # 04-distributed / 05-failure
    "celery": frozenset({Signal.DISTRIBUTED, Signal.FAILURE}),
    "redis": frozenset({Signal.DISTRIBUTED}),
    "kombu": frozenset({Signal.DISTRIBUTED}),
    "kafka": frozenset({Signal.DISTRIBUTED}),
    "aiokafka": frozenset({Signal.DISTRIBUTED}),
    "confluent_kafka": frozenset({Signal.DISTRIBUTED}),
    "pika": frozenset({Signal.DISTRIBUTED}),
    "aio_pika": frozenset({Signal.DISTRIBUTED}),
    "rq": frozenset({Signal.DISTRIBUTED}),
    "arq": frozenset({Signal.DISTRIBUTED}),
    "dramatiq": frozenset({Signal.DISTRIBUTED}),
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
    "os": frozenset({Signal.SECURITY}),
    "pickle": frozenset({Signal.SECURITY}),
    "shelve": frozenset({Signal.SECURITY}),
    "marshal": frozenset({Signal.SECURITY}),
    "yaml": frozenset({Signal.SECURITY}),
    "cryptography": frozenset({Signal.SECURITY}),
    "bcrypt": frozenset({Signal.SECURITY}),
    "passlib": frozenset({Signal.SECURITY}),
    "authlib": frozenset({Signal.SECURITY}),
    # entrypoints
    "fastapi": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
    "flask": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
    # Django is a web framework and an ORM; routing it to the network
    # specialist alone sent every models.py to the one reviewer that could
    # say nothing about it.
    "django": frozenset({Signal.ENTRYPOINT, Signal.NETWORK, Signal.DATA}),
    "starlette": frozenset({Signal.ENTRYPOINT, Signal.NETWORK}),
}


# Imports that carry no engineering concern for any specialist. Naming them
# keeps `unmatched_imports` meaningful: without this, "no detector matched"
# fires on `import sys` and stops distinguishing a gap in our table from a
# module that genuinely has nothing to review.
INERT_IMPORTS = frozenset(
    {
        "__future__",
        "abc",
        "argparse",
        "collections",
        "contextlib",
        "copy",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "inspect",
        "io",
        "itertools",
        "json",
        "math",
        "operator",
        "pathlib",
        "pprint",
        "re",
        "shutil",
        "string",
        "sys",
        "tempfile",
        "textwrap",
        "time",
        "types",
        "typing",
        "unittest",
        "uuid",
        "warnings",
        "weakref",
        "pytest",
        "pydantic",
        "attrs",
        "click",
        "rich",
        "typer",
        "numpy",
        "pandas",
        "matplotlib",
    }
)


def signals_for_import(top_level: str) -> frozenset[Signal]:
    return IMPORT_SIGNALS.get(top_level, frozenset())


def is_inert(top_level: str) -> bool:
    """True when nothing is missing: this import has no concern to review."""
    return top_level in INERT_IMPORTS
