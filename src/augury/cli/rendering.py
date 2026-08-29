"""Turning what the survey found into something a person reads in one pass.

Both functions here exist because of what real output looked like, not
because of what the code suggested it would look like. A service command
truncated to fit a column cut off `--concurrency=1` -- the single fact the
survey exists to surface, since it appears in no source file -- and the
language mix printed as `{'python': 224}`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rich.table import Column, Table

from augury.core.survey.model import Service

# Flags that cap how much work a process will do at once. A reviewer reading
# only source cannot see any of them: they are declared by the deployment.
_CEILINGS = (
    "--concurrency",
    "--pool",
    "--prefetch-multiplier",
    "--workers",
    "--max-tasks-per-child",
    "--threads",
    "--worker-class",
    "--backlog",
    "--limit-max-requests",
)


def capacity_flags(command: str) -> str:
    """The parts of a service command that declare a capacity ceiling.

    Empty when the command declares none, which is itself worth showing as
    blank rather than as a shortened command that implies one was there.
    """
    words = command.split()
    kept: list[str] = []
    for index, word in enumerate(words):
        name = word.split("=", 1)[0]
        if name not in _CEILINGS:
            continue
        if "=" in word:
            kept.append(word)
        elif index + 1 < len(words):
            # `--workers 4` rather than `--workers=4`. Both forms are common
            # and a ceiling shown without its value is not a ceiling.
            kept.append(f"{word} {words[index + 1]}")
        else:
            kept.append(word)
    return " ".join(kept)


def languages_read(counts: dict[str, int]) -> str:
    """The language mix as prose, largest first.

    Largest first because the question a reader has is "what is this service
    written in", and alphabetical order answers a question nobody asked.
    """
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ", ".join(f"{count} {name}" for name, count in ordered)


def runs_summary(command: str, ports: tuple[str, ...] = ()) -> str:
    """What a service actually runs, short enough to sit in a column.

    Six Celery workers built from one directory share the first forty
    characters of their commands, so a prefix cut renders them identical. The
    queue is what tells them apart, and it comes after the shared part.
    """
    words = command.split()
    if not words:
        # An image with its own entrypoint. The published port is the only
        # thing the compose file says about it, and it is the thing that
        # distinguishes the service requests arrive at from the five that
        # take work off a queue.
        listens = _container_port(ports[0]) if ports else ""
        return f"serves :{listens}" if listens else ""

    program = words[0]
    if program == "celery":
        return f"celery {_celery_role(words)}"
    if program in _COLON_RUNNERS:
        target = next((w for w in words[1:] if ":" in w and not w.startswith("-")), "")
        return f"{program} {target}".strip()
    return program


# Servers named by `program module:attribute`. Kept here rather than imported
# from the surveyor: this list answers "how do I print it", not "what does it
# start", and the two drift for different reasons.
_COLON_RUNNERS = frozenset({"uvicorn", "gunicorn", "hypercorn", "daphne", "granian"})


def _celery_role(words: list[str]) -> str:
    if "beat" in words:
        return "beat"
    if "flower" in words:
        return "flower"
    for index, word in enumerate(words):
        if word in {"-Q", "--queues"} and index + 1 < len(words):
            return f"worker -Q {words[index + 1]}"
    return "worker"


def service_table(services: Sequence[Service]) -> Table:
    """The compose file's services, as a reader needs them.

    Capacity folds rather than ellipsizes. A ceiling shown as
    `--concurrenc…` is a ceiling nobody can read, and this table is recorded
    in a terminal rather than viewed in a wide editor.
    """
    table = Table(
        Column("service", overflow="fold"),
        Column("built from", overflow="fold"),
        Column("runs", overflow="fold"),
        Column("capacity", overflow="fold"),
    )
    for service in services:
        table.add_row(
            service.name,
            service.source_root or ".",
            runs_summary(service.command, service.ports) or "-",
            capacity_flags(service.command) or "-",
        )
    return table


def _container_port(mapping: str) -> str:
    """The port inside the container, from a compose `ports` entry.

    A platform that injects the port writes `${PORT:-10000}:${PORT:-10000}`,
    where splitting on `:` finds the `:-` of the shell default rather than
    the mapping. Taking the last run of digits avoids having to know which
    colon was which.
    """
    digits = re.findall(r"\d+", mapping)
    return digits[-1] if digits else ""
