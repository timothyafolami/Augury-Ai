"""What the deployment declares, and what is wrong with it.

Each rule is a fact about a Dockerfile, a compose file, a Procfile, a manifest
or a workflow rather than a judgement, which is why none of them costs a model
call. Each names the remediation, because a finding that does not is a
complaint.

The defects here are not in any source file. `FROM python:3.13-slim` with no
`USER` is two correct lines that hand a container escape uid 0, and
`--workers $(nproc)` is one correct line that asks for 17 processes under a
2-CPU quota. No per-module review reaches either, because the module is right;
what is wrong is the machine it is told to run on.

Every number below is derived from something declared in the artefacts, or is
a documented constant of the thing being described -- SIGKILL is signal 9,
Postgres reserves 3 connections for superusers. Nothing here estimates.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

import yaml

# Reused rather than restated, for the reason the reader reuses the mapper's
# exclusions. The security rule especially: two predicates for "may this file
# be opened" is one convention away from the looser of them reading a live key
# into a prompt, a printed report and a committed recording, from which it can
# only be removed by rotating it.
from augury.core.artifacts.reader import (
    LOCKFILE_ECOSYSTEMS,
    LOCKS_FOR,
    holds_live_credentials,
)
from augury.core.schema.model import SchemaFinding

# Postgres reserves connections for superusers so an operator can still get in
# when the pool has eaten everything. That reservation is why the budget is 97
# and not 100, and it is the difference between "degraded" and "you cannot log
# in to fix it".
SUPERUSER_RESERVED = 3

# The reader's own cap on a configuration file, restated as a bound on what
# these rules will open when they read from disk. A vendored bundle with a
# .yaml extension is not a declaration about the deployment.
_MAX_ARTIFACT_BYTES = 128 * 1024

# The host size every worker-count formula is quietly written for. It is not a
# guess about the reader's fleet: it is the arithmetic that makes the failure
# legible, because `2 * cpu_count + 1` returns 17 there and 17 is the number
# people recognise from their own compose file.
_ASSUMED_HOST_CPUS = 8


class Artifact(Protocol):
    """One deployment declaration the reader found.

    `augury.core.artifacts.reader` owns discovery and typing; this module owns
    the rules. Structural rather than imported, because the two models differ
    on purpose: the reader carries per-kind facts because the inventory is sent
    with a review, and these rules need the file as written because a finding
    that cannot name a line is a finding nobody can open.

    `text` is deliberately not a member. An artefact that has one is read from
    it; the reader's does not, so `deployment_findings` is given a `root` and
    reads the file itself. A lockfile is never opened either way: it earns its
    place in the inventory by existing.
    """

    @property
    def kind(self) -> str: ...

    @property
    def path(self) -> str: ...


# -- the file that is never opened ----------------------------------------


def is_secret_env(path: str) -> bool:
    """Whether this path is a .env holding live credentials.

    A .env is never read, parsed, mapped or summarised, and it is not redacted
    afterwards, because the read is the leak: a finding reaches a model, a
    printed report and a committed recording, and a credential belongs in none
    of the three. `.env.example` and `.env.sample` are committed files listing
    variable names, so they are safe and occasionally useful.

    The decision itself is the reader's, on its allowlist. This wrapper only
    turns a path into the name that allowlist is written against, so that a
    check reaching in with `backend/.env` gets the same answer as the walk that
    refused to inventory it.
    """
    return holds_live_credentials(PurePosixPath(path).name)


# -- classification --------------------------------------------------------

_LOCKFILES = frozenset(LOCKFILE_ECOSYSTEMS)

# The lockfile each manifest's own tooling writes, taken from the reader so
# that a manifest kind added there is covered here without being added twice.
# A Cargo.lock beside a package.json locks nothing that package.json declares.
#
# requirements.in is added because pip-compile's output is that manifest's
# lockfile. requirements.txt is deliberately still absent: pip has no lockfile
# format for one to be missing, and the unpinned entries inside it are already
# reported by the dependency checks, so reporting both would be one defect
# counted twice.
_LOCKS_FOR: dict[str, tuple[str, ...]] = {
    **LOCKS_FOR,
    "requirements.in": ("requirements.txt",),
}

# How each ecosystem is told to write the file. Consulted by name rather than
# indexed, so that a manifest the reader learns about later still produces a
# finding here instead of a KeyError.
_LOCK_COMMAND = {
    "pyproject.toml": "uv lock",
    "Pipfile": "pipenv lock",
    "requirements.in": "pip-compile requirements.in",
    "package.json": "npm install --package-lock-only",
    "Cargo.toml": "cargo generate-lockfile",
    "go.mod": "go mod tidy",
    "Gemfile": "bundle lock",
    "composer.json": "composer update --lock",
}

_COMPOSE_NAME = re.compile(r"^(docker-)?compose[.\w-]*\.ya?ml$")

# The reader's vocabulary may drift as it is written. A kind we do not know
# falls back to the filename, so a renamed constant over there degrades one
# artefact rather than silently switching off every check here.
_KIND_SYNONYMS = {
    "dockerfile": "dockerfile",
    "docker": "dockerfile",
    "compose": "compose",
    "docker-compose": "compose",
    "procfile": "procfile",
    "manifest": "manifest",
    "dependencies": "manifest",
    "lockfile": "lockfile",
    "lock": "lockfile",
    "workflow": "workflow",
    "ci": "workflow",
    "dotenv": "dotenv",
    "env": "dotenv",
}


def _kind(artifact: Artifact) -> str:
    declared = artifact.kind.strip().lower().replace("_", "-")
    return _KIND_SYNONYMS.get(declared) or _kind_of_path(artifact.path)


def _kind_of_path(path: str) -> str:
    name = PurePosixPath(path).name
    lowered = name.lower()
    if is_secret_env(path):
        return "dotenv"
    if lowered.startswith("dockerfile") or lowered.endswith(".dockerfile"):
        return "dockerfile"
    if _COMPOSE_NAME.match(lowered):
        return "compose"
    if lowered == "procfile":
        return "procfile"
    if ".github/workflows/" in path and lowered.endswith((".yml", ".yaml")):
        return "workflow"
    if name in _LOCKFILES:
        return "lockfile"
    if name in _LOCKS_FOR:
        return "manifest"
    return "other"


# -- the entry point -------------------------------------------------------


def deployment_findings(
    artifacts: Iterable[Artifact], *, root: Path | None = None
) -> tuple[SchemaFinding, ...]:
    """Every deterministic defect these deployment artefacts carry.

    `root` is the repository the inventory was read from. It is needed when the
    artefacts carry no text of their own, which is the reader's shape: it keeps
    facts rather than contents, so the file has to be opened here to say which
    line a finding is on.
    """
    # The .env is dropped before anything asks for its contents, and before its
    # kind is even consulted. The reader already refused to inventory one, so
    # this is the second of two independent refusals rather than the only one --
    # a caller may hand these rules any sequence it likes.
    inventory = [artifact for artifact in artifacts if not is_secret_env(artifact.path)]
    typed = [(_kind(artifact), artifact, _text_of(artifact, root)) for artifact in inventory]
    paths = frozenset(artifact.path for artifact in inventory)
    # A repository with a compose file declares its probes there. Reporting
    # the Dockerfile as well is the same finding twice, and two findings for
    # one defect is how a report stops being read.
    has_compose = any(kind == "compose" for kind, _, _ in typed)

    found: list[SchemaFinding] = []
    for kind, artifact, text in typed:
        if kind == "dockerfile":
            found.extend(_dockerfile(artifact.path, text, alone=not has_compose))
        elif kind == "compose":
            found.extend(_compose(artifact.path, text))
        elif kind == "procfile":
            found.extend(_procfile(artifact.path, text))
        elif kind == "manifest":
            found.extend(_manifest(artifact.path, paths))
        elif kind == "workflow":
            found.extend(_workflow(artifact.path, text))

    # Sorted rather than emitted in inventory order. Determinism has to
    # survive a reader that walks the repository in a different order on a
    # different filesystem, and a report whose lines move between runs cannot
    # be diffed against the previous one.
    return tuple(sorted(found, key=lambda f: (f.path, f.line, f.rule)))


def _text_of(artifact: Artifact, root: Path | None) -> str:
    """The file as written, from the artefact or from disk.

    Best-effort in the same way the mapper and the reader are: a file that
    cannot be opened is a reason to know less about the repository, not a
    reason to refuse to review it. An unreadable artefact simply produces no
    findings, which is the honest answer rather than a guessed one.
    """
    carried = getattr(artifact, "text", None)
    if isinstance(carried, str):
        return carried
    if root is None:
        return ""
    path = Path(root) / artifact.path
    try:
        if path.is_symlink() or path.stat().st_size > _MAX_ARTIFACT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# -- Dockerfile ------------------------------------------------------------


@dataclass(frozen=True)
class _Instruction:
    keyword: str
    argument: str
    line: int


def _instructions(text: str) -> list[_Instruction]:
    """Every instruction, with the line its first token sits on.

    Continuations are joined, because a CMD broken across lines with a trailing
    backslash puts its arithmetic on a line that begins with no keyword at all.
    The line reported is the one the instruction starts on, which is the line a
    reader opening the file will recognise.
    """
    found: list[_Instruction] = []
    pending = ""
    start = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#") or (not line and not pending):
            continue
        if not pending:
            start = number
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        keyword, _, argument = (pending + line).strip().partition(" ")
        pending = ""
        if keyword:
            found.append(_Instruction(keyword.upper(), argument.strip(), start))
    return found


def _final_stage(instructions: list[_Instruction]) -> list[_Instruction]:
    """The instructions that survive into the shipped image.

    A multi-stage build discards everything before the last FROM, so a `USER`
    in the builder stage protects nothing and a `HEALTHCHECK` in it ships
    nowhere.
    """
    starts = [index for index, item in enumerate(instructions) if item.keyword == "FROM"]
    return instructions[starts[-1] :] if starts else []


def _dockerfile(path: str, text: str, *, alone: bool) -> list[SchemaFinding]:
    instructions = _instructions(text)
    # A file that yielded no instructions was not read: too large, unreadable,
    # or carried by an artefact that keeps facts rather than contents. Every
    # rule below is about something the file does not say, and "says nothing"
    # is not the same fact as "was never opened". Reporting the second as the
    # first is the invented finding this tool exists not to produce.
    if not instructions:
        return []
    stage = _final_stage(instructions)
    found: list[SchemaFinding] = []

    if stage and not any(_drops_privilege(item) for item in stage):
        found.append(
            SchemaFinding(
                rule="container-runs-as-root",
                path=path,
                line=stage[0].line,
                detail=(
                    "the final stage declares no USER, so every process in the "
                    "shipped image runs as uid 0. A container escape from it is a "
                    "root escape, every bind-mounted host path is writable, and the "
                    "process can bind privileged ports it never needed"
                ),
                remediation=(
                    "Add `RUN useradd --system --create-home app` and a `USER app` "
                    "line before the CMD, then chown the paths the process writes to"
                ),
            )
        )

    found.extend(_latest_in_dockerfile(path, instructions))

    if alone and not any(item.keyword == "HEALTHCHECK" for item in instructions):
        found.append(_no_probe_in_dockerfile(path, stage, instructions))

    for item in stage:
        if item.keyword not in {"CMD", "ENTRYPOINT"}:
            continue
        finding = _quota_blind(path, item.line, item.argument)
        if finding is not None:
            found.append(finding)

    return found


def _drops_privilege(item: _Instruction) -> bool:
    """Whether this instruction leaves uid 0.

    `USER root` is a decision rather than an oversight, and it is still uid 0.
    """
    if item.keyword != "USER":
        return False
    user = item.argument.split(":")[0].strip()
    return bool(user) and user not in {"root", "0"}


def _no_probe_in_dockerfile(
    path: str, stage: list[_Instruction], instructions: list[_Instruction]
) -> SchemaFinding:
    entry = next((i for i in reversed(stage) if i.keyword in {"CMD", "ENTRYPOINT"}), None)
    anchor = entry.line if entry is not None else (stage[0].line if stage else 1)
    exposed = next(
        (i.argument.split("/")[0].strip() for i in instructions if i.keyword == "EXPOSE"), ""
    )
    port = exposed or "<port>"
    return SchemaFinding(
        rule="no-healthcheck",
        path=path,
        line=anchor,
        detail=(
            "this process ships with no HEALTHCHECK, so nothing distinguishes a "
            "wedged one from a busy one. A worker that still holds its listening "
            "socket while making no progress stays marked healthy, keeps being "
            "given requests, and is never restarted because nothing is asking"
        ),
        remediation=(
            "Add `HEALTHCHECK --interval=10s --timeout=2s --retries=3 CMD "
            f"curl -fsS http://localhost:{port}/healthz || exit 1`, on a route that "
            "touches the dependency this process needs rather than one that returns "
            "200 unconditionally"
        ),
    )


_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _latest_in_dockerfile(path: str, instructions: list[_Instruction]) -> list[SchemaFinding]:
    """Images pulled through a mutable tag.

    `ARG PYTHON_IMAGE=python:3.13-slim` followed by `FROM ${PYTHON_IMAGE}` is
    pinned, and reporting it would be wrong. Build args are resolved to their
    declared defaults before the tag is read.
    """
    defaults: dict[str, str] = {}
    aliases: set[str] = set()
    found: list[SchemaFinding] = []
    for item in instructions:
        if item.keyword == "ARG":
            name, sep, value = item.argument.partition("=")
            if sep:
                defaults[name.strip()] = value.strip()
            continue
        if item.keyword != "FROM":
            continue
        reference, alias = _from_reference(item.argument)
        resolved = _expand(reference, defaults)
        # `FROM builder` names an earlier stage in this same file. No registry
        # is consulted, so there is no tag to be mutable.
        if resolved not in aliases and _is_mutable_tag(resolved):
            found.append(_latest_finding(path, item.line, resolved))
        if alias:
            aliases.add(alias)
    return found


def _from_reference(argument: str) -> tuple[str, str]:
    tokens = [token for token in argument.split() if not token.startswith("--")]
    if not tokens:
        return "", ""
    alias = ""
    if len(tokens) >= 3 and tokens[-2].upper() == "AS":
        alias = tokens[-1]
    return tokens[0], alias


def _expand(value: str, defaults: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(3)
        return defaults.get(name, match.group(2) or "")

    return _VARIABLE.sub(replace, value)


def _is_mutable_tag(reference: str) -> bool:
    """An image reference that can resolve to a different digest tomorrow."""
    if not reference or "$" in reference or reference == "scratch":
        return False
    # Only the last path segment can hold the tag, because a registry host may
    # carry a port: `registry.local:5000/app` is untagged rather than tagged
    # `5000/app`. A digest is pinned under the same rule and needs no branch of
    # its own, since `app@sha256:...` puts a colon in that segment too.
    last = reference.rsplit("/", 1)[-1]
    return ":" not in last or last.rsplit(":", 1)[1] == "latest"


def _latest_finding(path: str, line: int, reference: str) -> SchemaFinding:
    untagged = f"{reference} (no tag, so :latest)"
    tagged = reference if ":" in reference.rsplit("/", 1)[-1] else untagged
    return SchemaFinding(
        rule="latest-tag",
        path=path,
        line=line,
        detail=(
            f"`{tagged}` is a mutable pointer, so the digest it resolves to changes "
            "without this file changing. Two builds of this commit are two different "
            "services, and redeploying the same tag rolls nothing back because the "
            "tag already moved"
        ),
        remediation=(
            f"Pin it by digest: `docker buildx imagetools inspect {reference}` prints "
            "the sha256, then write the reference as `image@sha256:...` and let a "
            "bot raise the pull request that moves it"
        ),
    )


# -- the worker count ------------------------------------------------------

# Calls that answer a question nobody asked. None of them reads
# /sys/fs/cgroup/cpu.max, which is the number the kernel actually enforces.
_CPU_CALLS = (
    "nproc",
    "os.cpu_count()",
    "multiprocessing.cpu_count()",
    "os.process_cpu_count()",
    "os.sched_getaffinity",
    "os.cpus().length",
    "runtime.NumCPU()",
    "availableProcessors()",
)

_DOUBLED = re.compile(r"2\s*\*")


def _quota_blind(path: str, line: int, command: str) -> SchemaFinding | None:
    """The worker count computed from the host rather than from the quota."""
    call = next((candidate for candidate in _CPU_CALLS if candidate in command), None)
    if call is None:
        return None

    if _DOUBLED.search(command):
        # 2 * 8 + 1. Not a typo, and not a number this tool chose: it is what
        # the most-copied line in Python deployment guides returns.
        count = 2 * _ASSUMED_HOST_CPUS + 1
        arithmetic = f"2 * {_ASSUMED_HOST_CPUS} + 1 = {count}"
    else:
        count = _ASSUMED_HOST_CPUS
        arithmetic = f"{count}"

    return SchemaFinding(
        rule="workers-ignore-the-cpu-quota",
        path=path,
        line=line,
        detail=(
            f"the worker count comes from `{call}`, which reports the host's logical "
            "CPUs and is blind to the bandwidth quota in cpu.max. On an 8-core host "
            f"that is {arithmetic} workers; under a 2-CPU quota those {count} "
            "processes share 2 CPUs of bandwidth, so the surplus buys no throughput "
            "at all and every request pays the queueing and the throttled tail"
        ),
        remediation=(
            "Take the count from the deployment that already set the quota: "
            "`--workers ${WORKERS}` with WORKERS declared beside the `cpus:` limit, "
            "at floor(quota) for CPU-bound work"
        ),
    )


# -- compose ---------------------------------------------------------------


def _yaml(text: str) -> object:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _sequence(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


_SHELL_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}")


def _integer(value: object) -> int | None:
    """The number this declaration settles on, or None if it does not settle.

    `${WORKERS:-4}` is 4 in every deployment that does not override it, which
    makes it a visible part. `${WORKERS}` is not: the value lives somewhere
    this review cannot see, and inventing one would be the fabrication the
    whole tool exists to avoid.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isdigit():
        return int(text)
    match = _SHELL_DEFAULT.search(text)
    if match is not None and match.group(1).strip().isdigit():
        return int(match.group(1).strip())
    return None


def _environment(spec: dict[str, object]) -> dict[str, str]:
    raw = spec.get("environment")
    if isinstance(raw, dict):
        return {str(key): "" if item is None else str(item) for key, item in raw.items()}
    found: dict[str, str] = {}
    for item in _sequence(raw):
        key, sep, value = str(item).partition("=")
        if sep:
            found[key.strip()] = value.strip()
    return found


def _service_command(spec: dict[str, object]) -> str:
    raw = spec.get("command")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return " ".join(str(item) for item in raw)
    return ""


def _key_line(text: str, name: str) -> int:
    """The line a compose service is declared on.

    Read from the text rather than from the parsed document: PyYAML discards
    positions, and a finding without a line is a finding nobody can open.
    """
    inside = False
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped == "services:":
            inside = True
            continue
        if inside and stripped.startswith(f"{name}:") and raw != raw.lstrip():
            return number
    return 1


def _line_containing(text: str, needle: str, default: int = 1) -> int:
    for number, raw in enumerate(text.splitlines(), start=1):
        if needle and needle in raw:
            return number
    return default


def _trigger_line(text: str) -> int:
    """The line a workflow's `on:` block starts on.

    Anchored to column zero rather than searched for: `runs-on:` contains the
    same three characters, and a workflow that declares its jobs above its
    triggers would send the reader to the wrong line.
    """
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith(("on:", "'on':", '"on":')):
            return number
    return 1


_POOL_KEYS = frozenset(
    {"POOL_SIZE", "POOL_MAX", "DB_POOL_SIZE", "DATABASE_POOL_SIZE", "SQLALCHEMY_POOL_SIZE"}
)
_OVERFLOW_KEYS = frozenset(
    {"MAX_OVERFLOW", "DB_MAX_OVERFLOW", "POOL_MAX_OVERFLOW", "SQLALCHEMY_MAX_OVERFLOW"}
)
_WORKER_KEYS = ("WORKERS", "WEB_CONCURRENCY", "GUNICORN_WORKERS", "UVICORN_WORKERS")
_WORKER_FLAG = re.compile(r"(?:^|\s)(?:--workers|--concurrency|-w)[=\s]+(\S+)")
_MAX_CONNECTIONS = re.compile(r"max_connections\s*=\s*(\d+)")
_DATABASE_IMAGES = ("postgres", "postgis", "timescale")


def _compose(path: str, text: str) -> list[SchemaFinding]:
    services = _mapping(_mapping(_yaml(text)).get("services"))
    if not services:
        return []

    declared_limit = next(
        (
            limit
            for spec in services.values()
            if (limit := _MAX_CONNECTIONS.search(_service_command(_mapping(spec))))
        ),
        None,
    )
    # Postgres is compiled with max_connections 100. When the compose file
    # declares its own, that one wins; the fallback is named as a default in
    # the finding rather than presented as something that was read.
    max_connections = int(declared_limit.group(1)) if declared_limit else 100
    has_database = any(
        any(marker in str(_mapping(spec).get("image", "")) for marker in _DATABASE_IMAGES)
        for spec in services.values()
    )

    found: list[SchemaFinding] = []
    for raw_name, raw_spec in services.items():
        name = str(raw_name)
        spec = _mapping(raw_spec)
        line = _key_line(text, name)
        found.extend(_service(path, name, spec, line))
        if has_database:
            found.extend(
                _connection_arithmetic(
                    path, name, spec, line, max_connections, bool(declared_limit)
                )
            )
    return found


def _service(path: str, name: str, spec: dict[str, object], line: int) -> list[SchemaFinding]:
    found: list[SchemaFinding] = []

    if not _has_memory_limit(spec):
        found.append(_no_memory_limit(path, name, line))

    if _sequence(spec.get("ports")) and "healthcheck" not in spec:
        found.append(_no_probe(path, name, line))

    image = str(spec.get("image", ""))
    if _is_mutable_tag(image):
        found.append(_latest_finding(path, line, image))

    finding = _quota_blind(path, line, _service_command(spec))
    if finding is not None:
        found.append(finding)

    return found


def _has_memory_limit(spec: dict[str, object]) -> bool:
    """Either spelling. Compose v2 says `mem_limit`, v3 says `deploy.resources`
    and both end up writing the same memory.max."""
    if spec.get("mem_limit"):
        return True
    limits = _mapping(_mapping(_mapping(spec.get("deploy")).get("resources")).get("limits"))
    return bool(limits.get("memory"))


def _no_memory_limit(path: str, name: str, line: int) -> SchemaFinding:
    return SchemaFinding(
        rule="no-memory-limit",
        path=path,
        line=line,
        detail=(
            f"`{name}` declares no memory limit, so its cgroup has no ceiling and "
            "the kernel only intervenes once the whole host is out. The host OOM "
            "killer then picks its victim by badness score across every process on "
            "the machine, which is how one leaking container kills its neighbours. "
            "Under a limit the cgroup's own OOM killer picks inside this cgroup and "
            "sends SIGKILL, which a shell reports as 128 + 9 = exit 137: no "
            "MemoryError, no traceback, no atexit hook, no shutdown log line"
        ),
        remediation=(
            f"Add `mem_limit:` to `{name}`, sized from the RSS `docker stats` reports "
            "at peak rather than ten seconds after start: early RSS understates the "
            "steady state, and for a forked worker pool it understates it badly, "
            "because copy-on-write pages un-share as refcounts are written into them"
        ),
    )


def _no_probe(path: str, name: str, line: int) -> SchemaFinding:
    return SchemaFinding(
        rule="no-healthcheck",
        path=path,
        line=line,
        detail=(
            f"`{name}` publishes ports and declares no healthcheck, so nothing "
            "distinguishes a wedged process from a busy one. A worker that still "
            "holds its listening socket while making no progress stays in rotation, "
            "keeps being handed requests, and is never restarted because nothing is "
            "asking it whether it is alive"
        ),
        remediation=(
            f"Add to `{name}` a `healthcheck:` whose `test` calls a route that "
            "touches the dependency it needs, with `interval` and `retries` "
            "multiplying to less than the client's timeout so the restart happens "
            "before the caller gives up"
        ),
    )


def _connection_arithmetic(
    path: str,
    name: str,
    spec: dict[str, object],
    line: int,
    max_connections: int,
    declared: bool,
) -> list[SchemaFinding]:
    """replicas x workers x (pool_size + max_overflow) against the budget.

    Nothing in Docker, Kubernetes, uvicorn, SQLAlchemy or Postgres computes
    this product or warns when it exceeds the limit, which is why "we scaled
    up and it got slower" is a stock incident.

    Reported only when every factor is declared. A product with a guessed
    factor in it is a fabricated number, and this tool's whole claim is that
    it does not invent them.
    """
    environment = _environment(spec)
    workers = _workers(_service_command(spec), environment)
    pool = _first_integer(environment, _POOL_KEYS)
    if workers is None or pool is None:
        return []

    overflow = _first_integer(environment, _OVERFLOW_KEYS) or 0
    replicas = _integer(_mapping(spec.get("deploy")).get("replicas")) or 1
    per_worker = pool + overflow
    worst_case = replicas * workers * per_worker
    budget = max_connections - SUPERUSER_RESERVED
    if worst_case <= budget:
        return []

    source = "declared here" if declared else "the default Postgres is compiled with"
    fits_workers = budget // max(1, replicas * per_worker)
    fits_pool = budget // max(1, replicas * workers) - overflow
    return [
        SchemaFinding(
            rule="quota-without-replicas-arithmetic",
            path=path,
            line=line,
            detail=(
                f"`{name}` opens {replicas} replicas x {workers} workers x "
                f"({pool} pool + {overflow} overflow) = {worst_case} backends at "
                f"worst, against max_connections {max_connections} ({source}) less "
                f"the {SUPERUSER_RESERVED} Postgres reserves for superusers: a "
                f"budget of {budget}, over by {worst_case - budget}. Each backend is "
                "a real process with real memory, so the database slows down for "
                "everyone before it starts refusing, and the reserved connections "
                "are what stops the operator being locked out while it does"
            ),
            remediation=(
                f"Make the product fit: at {replicas} replicas that is "
                f"{fits_workers} workers, or a pool of {max(0, fits_pool)} at "
                f"{workers} workers. If you need more concurrency than that allows, "
                "put pgbouncer in transaction mode in front of it rather than "
                "raising the pool"
            ),
        )
    ]


def _workers(command: str, environment: dict[str, str]) -> int | None:
    match = _WORKER_FLAG.search(command)
    if match is not None:
        found = _integer(match.group(1))
        if found is not None:
            return found
    for key in _WORKER_KEYS:
        if key in environment:
            found = _integer(environment[key])
            if found is not None:
                return found
    return None


def _first_integer(environment: dict[str, str], keys: frozenset[str]) -> int | None:
    for key in sorted(keys):
        if key in environment:
            found = _integer(environment[key])
            if found is not None:
                return found
    return None


# -- Procfile --------------------------------------------------------------


def _procfile(path: str, text: str) -> list[SchemaFinding]:
    found: list[SchemaFinding] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        _, sep, command = line.partition(":")
        if not sep:
            continue
        finding = _quota_blind(path, number, command)
        if finding is not None:
            found.append(finding)
    return found


# -- manifests -------------------------------------------------------------


def _manifest(path: str, paths: frozenset[str]) -> list[SchemaFinding]:
    """The manifest whose lockfile is not beside it.

    The reader summarises the same set on its Inventory as
    `manifests_without_a_lockfile`, and does not judge it. This is where the
    mechanism and the remediation are attached, so there is one rule and one
    summary rather than two rules that can disagree.
    """
    name = PurePosixPath(path).name
    expected = _LOCKS_FOR.get(name)
    if expected is None:
        return []
    # Beside this manifest, not anywhere in the tree. A frontend's
    # package-lock.json locks nothing the backend's package.json declares.
    directory = PurePosixPath(path).parent
    if any(str(directory / lock) in paths for lock in expected):
        return []

    return [
        SchemaFinding(
            rule="lockfile-missing",
            path=path,
            line=1,
            detail=(
                f"`{name}` declares dependencies with no {expected[0]} beside it, so "
                "the resolver picks the newest version matching each range on the "
                "day of the build. Two builds of this commit install two different "
                "transitive trees, and the tree that broke production is not the one "
                "the tests passed against"
            ),
            remediation=(
                f"{_write_it(name, expected[0])}, commit it, and change the build to "
                f"install from the lockfile rather than resolving {name} again"
            ),
        )
    ]


def _write_it(manifest: str, lockfile: str) -> str:
    command = _LOCK_COMMAND.get(manifest)
    return f"Run `{command}`" if command else f"Generate the {lockfile} with its own tool"


# -- workflows -------------------------------------------------------------

_TEST_COMMANDS = (
    "pytest",
    "tox",
    "nox",
    "npm test",
    "npm run test",
    "yarn test",
    "pnpm test",
    "jest",
    "vitest",
    "go test",
    "cargo test",
    "mvn test",
    "mvn verify",
    "gradle test",
    "dotnet test",
    "rspec",
    "phpunit",
    "ctest",
    "make check",
    "make test",
)
# `|| true` and its relatives discard the exit code the gate reads, so the
# job is green with a red test suite.
_SWALLOWED = ("|| true", "||true", "|| exit 0", "; true")
_GATING_TRIGGERS = frozenset({"pull_request", "pull_request_target", "merge_group"})


def _workflow(path: str, text: str) -> list[SchemaFinding]:
    document = _mapping(_yaml(text))
    if not document:
        return []

    # YAML 1.1 resolves a bare `on` key to the boolean True, which is how a
    # workflow with a perfectly good pull_request trigger gets read as having
    # none. PyYAML is a 1.1 parser, and `_mapping` stringifies keys, so the
    # trigger block arrives under "True" rather than under "on".
    triggers = document.get("on", document.get("True"))
    names = _trigger_names(triggers)

    soft: list[str] = []
    swallowed: list[str] = []
    runs_tests = False
    for job in _mapping(document.get("jobs")).values():
        specification = _mapping(job)
        job_soft = specification.get("continue-on-error") is True
        for raw_step in _sequence(specification.get("steps")):
            step = _mapping(raw_step)
            run = step.get("run")
            if not isinstance(run, str) or not _runs_tests(run):
                continue
            runs_tests = True
            if job_soft or step.get("continue-on-error") is True:
                soft.append(run)
            if any(marker in run for marker in _SWALLOWED):
                swallowed.append(run)

    if not runs_tests:
        return []

    # One finding per workflow. Push-only and swallowed are two spellings of
    # the same defect, and a reader who fixes the first will see the second.
    if not names & _GATING_TRIGGERS:
        listed = ", ".join(sorted(names)) or "nothing"
        return [
            _not_a_gate(
                path,
                _trigger_line(text),
                (
                    f"the tests run on {listed} and never on a pull request, so the "
                    "first red build is the one after the merge that caused it. A "
                    "suite nobody has to pass is a suite that is already failing on "
                    "somebody's branch"
                ),
                "Add `pull_request:` to this workflow's `on:` and mark the job "
                "required in the branch ruleset, so the merge button waits for it",
            )
        ]

    if soft:
        return [
            _not_a_gate(
                path,
                _line_containing(text, "continue-on-error"),
                (
                    "the test step carries `continue-on-error: true`, so the job "
                    "reports success with a failing suite and the required check is "
                    "green whatever the tests did"
                ),
                "Delete the `continue-on-error: true` from the test step; if it is "
                "there for a flaky test, quarantine that test instead",
            )
        ]

    if swallowed:
        return [
            _not_a_gate(
                path,
                _line_containing(text, swallowed[0].splitlines()[0].strip()),
                (
                    f"the test command ends `{swallowed[0].strip()}`, which discards "
                    "the exit code the gate reads. The step is the only thing that "
                    "could fail the job, and it has been told not to"
                ),
                "Remove the trailing `|| true` so the runner sees the test command's own exit code",
            )
        ]

    return []


def _not_a_gate(path: str, line: int, detail: str, remediation: str) -> SchemaFinding:
    return SchemaFinding(
        rule="ci-does-not-gate",
        path=path,
        line=line,
        detail=detail,
        remediation=remediation,
    )


def _trigger_names(triggers: object) -> frozenset[str]:
    if isinstance(triggers, str):
        return frozenset({triggers})
    if isinstance(triggers, dict):
        return frozenset(str(key) for key in triggers)
    if isinstance(triggers, list):
        return frozenset(str(item) for item in triggers)
    return frozenset()


def _runs_tests(run: str) -> bool:
    lowered = run.lower()
    return any(command in lowered for command in _TEST_COMMANDS)
