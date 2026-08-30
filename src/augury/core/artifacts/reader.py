"""Everything a repository ships that the map does not read.

The Cartographer walks source: .py, .ts, .go, .rs, .java, .cpp. A large share
of production defects is in none of them. The container that runs as root, the
deployment with a request and no limit, the workflow that merges without
running the tests, the manifest with no lockfile beside it. Each is a defect,
and each is invisible to a reviewer that only opens source files.

Layer 1e of the practice lab is the case in point. Seven topics about what a
process is allowed to do inside a container, zero of them covered, because the
facts live in cpu.max, memory.max and a Dockerfile rather than in any module.

This finds and classifies. It does not parse each format deeply and it does not
judge. What comes back is an inventory -- kind, path, and the few facts that
matter for that kind -- because the inventory is sent with a review and the
files are not. A Kubernetes manifest tree is megabytes; the six numbers in it
that change how a module reads are not.

Everything here is deterministic. These are declarations rather than
judgements, and a model asked to restate them would cost money to be right
slightly less often.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Reused rather than restated. That exclusion list has a real incident behind
# it -- three quarters of one repository's map was a vendored environment --
# and a second copy of it here would drift away from the first.
from augury.core.cartography.mapper import EXCLUDED_DIRS
from augury.core.survey.surveyor import COMPOSE_FILES


class ArtifactKind(StrEnum):
    """What a non-source file is, by what its defects look like."""

    DOCKERFILE = "dockerfile"  # what ships, and who it runs as
    COMPOSE = "compose"  # read by the survey, recorded here for completeness
    KUBERNETES = "kubernetes"  # limits, replicas, probes, autoscaling
    CI = "ci"  # whether anything has to pass before a merge
    WEBSERVER = "webserver"  # worker counts and timeouts
    LOCKFILE = "lockfile"  # what was actually resolved
    MANIFEST = "manifest"  # what was asked for
    PROCFILE = "procfile"  # what the platform is told to run
    TERRAFORM = "terraform"  # presence only, for now
    ENV_EXAMPLE = "env-example"  # which variables exist, never their values


class Artifact(BaseModel):
    """One non-source file, and the few facts worth carrying about it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ArtifactKind
    path: str = Field(min_length=1, description="Repo-relative POSIX path")
    facts: dict[str, str] = Field(
        default_factory=dict,
        description="What the file states, in its own words. A key is here "
        "only when the file said it, so nothing in this mapping is inferred.",
    )
    absent: tuple[str, ...] = Field(
        default=(),
        description="Instructions this kind was searched for and does not "
        "declare. A missing USER is a fact about the file; what the process "
        "then runs as is a claim the file does not support, so it is not made.",
    )


class Inventory(BaseModel):
    """Every artefact the repository ships, classified and capped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: str
    artifacts: tuple[Artifact, ...] = ()
    totals: dict[str, int] = Field(
        default_factory=dict,
        description="How many of each kind the walk found, before the per-kind "
        "cap. A cap that drops files silently reports a smaller repository "
        "than the one under review; this is what stops it being a lie.",
    )
    manifests_without_a_lockfile: tuple[str, ...] = Field(
        default=(),
        description="Manifests with no lockfile beside them. The manifest "
        "declares a range and only the lockfile says what was resolved, so "
        "without one the version reviewed is not the version deployed. "
        "Capped like everything else.",
    )

    def of(self, kind: ArtifactKind) -> tuple[Artifact, ...]:
        """Every artefact of one kind, in the order they were found."""
        return tuple(artifact for artifact in self.artifacts if artifact.kind is kind)

    @property
    def tests_gate_the_merge(self) -> bool:
        """Whether some workflow runs the tests on a pull request.

        False when no workflow declares triggers we can read, because then
        nothing here supports the claim that the merge is gated.
        """
        return any(
            "pull_request" in artifact.facts.get("triggers", "") and "tests" in artifact.facts
            for artifact in self.of(ArtifactKind.CI)
        )


# -- what gets read, and how much of it ------------------------------------

# Enough of any one kind to characterise a repository. A monorepo ships one
# Kubernetes manifest per service per environment, and the four hundredth
# changes no review while costing the same tokens as the first.
MAX_PER_KIND = 25

# A configuration file has no legitimate reason to be larger than this. The cap
# bounds memory and it stops a vendored bundle with a .yaml extension from
# being parsed at cost.
MAX_ARTIFACT_BYTES = 128 * 1024

# Enough COPY lines to show what enters the image, not enough to be a listing.
MAX_COPIES = 12

# Enough process types for any Procfile anyone has written.
MAX_PROCESSES = 10

# Enough variable names to see what the service is configured by.
MAX_ENV_NAMES = 60

# Caches of downloaded providers and packaged deploy bundles. Hundreds of
# megabytes of somebody else's artefacts, and absent from the mapper's list
# because no source file lives in either, so nothing has needed them until now.
ALSO_EXCLUDED = frozenset({".terraform", ".serverless"})


# -- the security rule -----------------------------------------------------

# Committed by convention, and by construction holding placeholders. These are
# the only spellings of a dotenv that may be opened.
SAFE_ENV_NAMES = frozenset(
    {".env.example", ".env.sample", ".env.template", ".env.dist", "env.example", "env.sample"}
)

# A variable name and nothing that could be a value. Applied to the safe files
# too, because "committed, so it holds no secret" describes what should be in
# them rather than what is.
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def holds_live_credentials(name: str) -> bool:
    """Whether this file may hold live credentials for the repository.

    Allowlisted by the safe names rather than blocklisted by the unsafe ones.
    `.env.local`, `.env.staging` and `.env.production` are every bit as live as
    `.env`, and a reader that lists what to refuse is one new convention away
    from reading a key into a prompt, a printed report and a committed
    recording -- from which it can only be removed by rotating it.
    """
    lowered = name.lower()
    if lowered in SAFE_ENV_NAMES:
        return False
    return lowered.startswith(".env")


# -- classification --------------------------------------------------------

DOCKERFILE_NAMES = frozenset({"dockerfile", "containerfile"})

CI_FILES = frozenset(
    {
        ".gitlab-ci.yml",
        ".travis.yml",
        "azure-pipelines.yml",
        "azure-pipelines.yaml",
        "jenkinsfile",
        "cloudbuild.yaml",
        "cloudbuild.yml",
        ".drone.yml",
        "bitbucket-pipelines.yml",
        "appveyor.yml",
    }
)
CI_DIRS = (".github/workflows", ".circleci", ".buildkite", ".woodpecker")

WEBSERVER_NAMES = frozenset(
    {
        "nginx.conf",
        "gunicorn.conf.py",
        "gunicorn_conf.py",
        "gunicorn.py",
        "uwsgi.ini",
        "uvicorn.json",
        "haproxy.cfg",
        "caddyfile",
    }
)

# Manifest to the lockfiles that would make its build reproducible.
LOCKS_FOR: dict[str, tuple[str, ...]] = {
    "package.json": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json"),
    "pyproject.toml": ("uv.lock", "poetry.lock", "pdm.lock"),
    "Pipfile": ("Pipfile.lock",),
    "go.mod": ("go.sum",),
    "Cargo.toml": ("Cargo.lock",),
    "Gemfile": ("Gemfile.lock",),
    "composer.json": ("composer.lock",),
}

# Manifests with no separate lockfile to expect. A requirements.txt is already
# the pinned file, so calling it unlocked would report a defect that is not one.
UNLOCKED_MANIFESTS: dict[str, str] = {
    "requirements.txt": "python",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
}

MANIFEST_ECOSYSTEMS: dict[str, str] = {
    "package.json": "javascript",
    "pyproject.toml": "python",
    "Pipfile": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "Gemfile": "ruby",
    "composer.json": "php",
    **UNLOCKED_MANIFESTS,
}

LOCKFILE_ECOSYSTEMS: dict[str, str] = {
    lock: MANIFEST_ECOSYSTEMS[manifest] for manifest, locks in LOCKS_FOR.items() for lock in locks
}

WORKLOAD_KINDS = frozenset(
    {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}
)


def read_artifacts(root: Path) -> Inventory:
    """Classify everything the repository ships that is not source code.

    One walk of the tree. Content is opened only for the kinds whose facts are
    in the content: a lockfile's presence is the fact and its 350KB of resolved
    hashes are not, so it is never read.
    """
    base = Path(root)
    files = sorted(_walk(base), key=lambda relative: (relative.count("/"), relative))
    beside = _by_directory(files)

    found: dict[ArtifactKind, list[Artifact]] = {}
    unlocked: list[str] = []
    for relative in files:
        for artifact in _artifacts_for(base, relative, beside):
            found.setdefault(artifact.kind, []).append(artifact)
            if artifact.kind is ArtifactKind.MANIFEST and "lockfile" in artifact.absent:
                unlocked.append(artifact.path)

    return Inventory(
        root=str(base),
        artifacts=tuple(
            artifact for kind in ArtifactKind for artifact in found.get(kind, [])[:MAX_PER_KIND]
        ),
        totals={kind.value: len(artifacts) for kind, artifacts in found.items()},
        manifests_without_a_lockfile=tuple(unlocked[:MAX_PER_KIND]),
    )


# -- traversal -------------------------------------------------------------


def _walk(root: Path) -> Iterator[str]:
    """Every repo-relative path worth looking at, as POSIX.

    Symlinks are refused for the reason the mapper refuses them: the name is
    attacker-controlled and the target is not, so `Dockerfile -> ~/.aws/
    credentials` is a valid repository whose credentials would be read,
    classified and carried into a prompt.
    """
    excluded = set(EXCLUDED_DIRS) | ALSO_EXCLUDED
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if excluded & set(parts[:-1]):
            continue
        # Before anything else touches it, and before its name is recorded
        # anywhere. A path is cheap to leak and expensive to un-leak.
        if holds_live_credentials(path.name):
            continue
        yield "/".join(parts)


def _by_directory(files: list[str]) -> dict[str, set[str]]:
    """Directory to the names of the files in it, for the lockfile question."""
    beside: dict[str, set[str]] = {}
    for relative in files:
        directory, _, name = relative.rpartition("/")
        beside.setdefault(directory, set()).add(name)
    return beside


def _artifacts_for(root: Path, relative: str, beside: dict[str, set[str]]) -> list[Artifact]:
    """Zero, one, or several artefacts from one file.

    Several because a Kubernetes file is a stream of documents, and a
    Deployment and its Service in one file are two things to know about.
    """
    name = relative.rpartition("/")[2]
    lowered = name.lower()
    path = root / relative

    if lowered in DOCKERFILE_NAMES or lowered.startswith("dockerfile."):
        return [_one(ArtifactKind.DOCKERFILE, relative, _dockerfile(_read(path)))]

    if lowered in COMPOSE_FILES:
        # The survey already parses this into services, commands and scope.
        # Reading it twice would give two answers to one question, and no way
        # to tell which of them is the stale one.
        return [
            Artifact(
                kind=ArtifactKind.COMPOSE,
                path=relative,
                facts={"read_by": "augury.core.survey.Surveyor"},
            )
        ]

    if _is_ci(relative, lowered):
        return [_one(ArtifactKind.CI, relative, _ci(_read(path)))]

    if lowered in WEBSERVER_NAMES or lowered.endswith(".nginx.conf"):
        return [_one(ArtifactKind.WEBSERVER, relative, _webserver(name, _read(path)))]

    if lowered.endswith(".conf"):
        # Named for the scenario rather than for the server. The practice lab
        # ships its nginx configuration as `ordered.conf` and `mismatched.conf`,
        # one per topic, and matching the literal name nginx.conf found none of
        # them -- while the timeout the two differ by is exactly the defect a
        # review of that layer exists to catch.
        text = _read(path)
        if NGINX_MARKERS.search(text):
            return [_one(ArtifactKind.WEBSERVER, relative, _webserver(name, text))]
        return []

    if name in LOCKFILE_ECOSYSTEMS:
        # Never read. Its presence is the fact; its content is 350KB of
        # resolved hashes that no reviewer and no model has a question about.
        return [
            Artifact(
                kind=ArtifactKind.LOCKFILE,
                path=relative,
                facts={"ecosystem": LOCKFILE_ECOSYSTEMS[name]},
            )
        ]

    if name in MANIFEST_ECOSYSTEMS:
        return [_one(ArtifactKind.MANIFEST, relative, _manifest(name, relative, beside))]

    if lowered == "procfile" or lowered.startswith("procfile."):
        return [_one(ArtifactKind.PROCFILE, relative, _procfile(_read(path)))]

    if name.endswith((".tf", ".tfvars")):
        return [Artifact(kind=ArtifactKind.TERRAFORM, path=relative)]

    if lowered in SAFE_ENV_NAMES:
        return [_one(ArtifactKind.ENV_EXAMPLE, relative, _env_example(_read(path)))]

    if name.endswith((".yml", ".yaml")):
        return _kubernetes(relative, _read(path))

    return []


def _is_ci(relative: str, lowered: str) -> bool:
    return lowered in CI_FILES or any(relative.startswith(f"{d}/") for d in CI_DIRS)


def _one(
    kind: ArtifactKind, relative: str, read: tuple[dict[str, str], tuple[str, ...]]
) -> Artifact:
    facts, absent = read
    return Artifact(kind=kind, path=relative, facts=facts, absent=absent)


def _read(path: Path) -> str:
    """The file, or empty if it is too large or unreadable.

    Best-effort by design, like the mapper: a file that cannot be read is a
    reason to know less about the repository, not to refuse to review it.
    """
    try:
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# -- dockerfiles -----------------------------------------------------------

# The instructions with a defect behind them. Filtering to these means a line
# inside a heredoc cannot be mistaken for an instruction.
_INSTRUCTIONS = frozenset({"FROM", "USER", "COPY", "ADD", "HEALTHCHECK"})


def _dockerfile(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    instructions = _instructions(text)
    facts: dict[str, str] = {}
    absent: list[str] = []

    stages = [argument for name, argument in instructions if name == "FROM"]
    if stages:
        # The last stage is what ships. A builder's base image is discarded,
        # and reporting it describes an image that never runs anywhere.
        facts["base_image"] = stages[-1].split()[0]

    users = [argument for name, argument in instructions if name == "USER"]
    if users:
        facts["user"] = users[-1]
    else:
        absent.append("USER")

    copies = [argument for name, argument in instructions if name in {"COPY", "ADD"}]
    if copies:
        # `COPY . /app` is how a .env, a .git and a set of credentials reach a
        # published image, so the arguments are kept as written.
        facts["copies"] = " | ".join(_without_flags(c) for c in copies[:MAX_COPIES])

    checks = [argument for name, argument in instructions if name == "HEALTHCHECK"]
    if checks:
        facts["healthcheck"] = checks[-1]
    else:
        absent.append("HEALTHCHECK")

    return facts, tuple(absent)


def _instructions(text: str) -> list[tuple[str, str]]:
    """Instruction name and argument, with continuation lines joined.

    A Dockerfile's most interesting instructions are routinely spread over
    five lines with trailing backslashes, and reading it line by line finds
    an argument that stops at the first one.
    """
    joined: list[str] = []
    carried = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            carried += f"{line[:-1].strip()} "
            continue
        joined.append(f"{carried}{line}".strip())
        carried = ""
    if carried:
        joined.append(carried.strip())

    found: list[tuple[str, str]] = []
    for line in joined:
        name, _, argument = line.partition(" ")
        if name.upper() in _INSTRUCTIONS:
            found.append((name.upper(), argument.strip()))
    return found


def _without_flags(argument: str) -> str:
    """`COPY --from=builder /install /usr/local` without the `--from`."""
    return " ".join(token for token in argument.split() if not token.startswith("--"))


# -- kubernetes ------------------------------------------------------------


def _kubernetes(relative: str, text: str) -> list[Artifact]:
    """One artefact per document that declares an apiVersion and a kind.

    A compose file and a workflow are YAML too, so the sniff is what stops
    every YAML file in a repository from being called a manifest. It is a
    substring check before a parse because parsing every YAML file in a
    monorepo to discover that none of them is Kubernetes costs real time.
    """
    if "apiVersion" not in text:
        return []
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return []

    found: list[Artifact] = []
    for document in documents:
        if not isinstance(document, dict) or "apiVersion" not in document:
            continue
        kind = str(document.get("kind") or "")
        if not kind:
            continue
        facts, absent = _kubernetes_facts(kind, document)
        found.append(
            Artifact(kind=ArtifactKind.KUBERNETES, path=relative, facts=facts, absent=absent)
        )
    return found


def _kubernetes_facts(
    kind: str, document: dict[str, Any]
) -> tuple[dict[str, str], tuple[str, ...]]:
    facts: dict[str, str] = {"kind": kind}
    absent: list[str] = []

    name = str((document.get("metadata") or {}).get("name") or "")
    if name:
        facts["name"] = name

    declared = document.get("spec")
    spec: dict[str, Any] = declared if isinstance(declared, dict) else {}
    for field, key in (
        ("replicas", "replicas"),
        ("minReplicas", "min_replicas"),
        ("maxReplicas", "max_replicas"),
    ):
        if spec.get(field) is not None:
            facts[key] = str(spec[field])

    containers = _containers(document)
    limits = [described for c in containers if (described := _resources(c, "limits"))]
    requests = [described for c in containers if (described := _resources(c, "requests"))]
    if limits:
        facts["limits"] = "; ".join(limits)
    if requests:
        facts["requests"] = "; ".join(requests)

    probes = sorted(
        {
            probe
            for container in containers
            for probe in ("liveness", "readiness", "startup")
            if container.get(f"{probe}Probe")
        }
    )
    if probes:
        facts["probes"] = ", ".join(probes)

    if kind in WORKLOAD_KINDS:
        # Only for things that run containers. A Service declares no resources
        # and reporting that it lacks limits would be a finding about nothing.
        if not limits:
            absent.append("resources.limits")
        if not requests:
            absent.append("resources.requests")
        absent.extend(f"{probe}Probe" for probe in ("liveness", "readiness") if probe not in probes)

    return facts, tuple(absent)


def _containers(node: Any) -> list[dict[str, Any]]:
    """Every container spec, wherever this workload's shape buries it.

    A Deployment nests them under spec.template.spec, a CronJob under
    spec.jobTemplate.spec.template.spec and a Pod puts them at the top. One
    search finds all three, so a workload kind nobody anticipated still
    reports its limits.
    """
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "containers" and isinstance(value, list):
                found.extend(item for item in value if isinstance(item, dict))
            else:
                found.extend(_containers(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_containers(item))
    return found


def _resources(container: dict[str, Any], bucket: str) -> str:
    resources = container.get("resources")
    values = resources.get(bucket) if isinstance(resources, dict) else None
    if not isinstance(values, dict) or not values:
        return ""
    described = " ".join(f"{key}={value}" for key, value in values.items())
    name = str(container.get("name") or "")
    return f"{name}: {described}" if name else described


# -- continuous integration ------------------------------------------------

# The commands that mean a test suite ran. Matched as substrings, because the
# step is usually a shell line with the command somewhere inside it.
TEST_COMMANDS = (
    "pytest",
    "make check",
    "make test",
    "npm test",
    "npm run test",
    "yarn test",
    "pnpm test",
    "go test",
    "cargo test",
    "mvn test",
    "gradle test",
    "dotnet test",
    "jest",
    "vitest",
    "rspec",
    "phpunit",
    "tox",
    "unittest",
)

# GitHub says `run`, GitLab says `script`, Buildkite says `commands`. A CI
# system nobody here has heard of usually spells it one of those too.
_STEP_KEYS = frozenset({"run", "uses", "script", "commands", "cmd", "before_script"})


def _ci(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    facts: dict[str, str] = {}
    absent: list[str] = []

    document = _yaml_mapping(text)
    commands = _commands_in(document) if document is not None else text.splitlines()

    test = _test_command(commands)
    if test:
        facts["tests"] = test
    else:
        absent.append("tests")

    triggers = _triggers(document) if document is not None else ()
    if triggers:
        facts["triggers"] = ", ".join(triggers)
        if "pull_request" not in triggers:
            absent.append("pull_request")
    # No triggers read means no claim about them. A Jenkinsfile is Groovy and
    # a GitLab pipeline gates on `rules`, and calling either of them ungated
    # because it has no `on:` block would be inventing a finding.

    return facts, tuple(absent)


def _triggers(document: dict[Any, Any]) -> tuple[str, ...]:
    """What the workflow runs on.

    `on` is a YAML 1.1 boolean, so a GitHub workflow's single most important
    key arrives from the parser as `True` rather than as the string `on`.
    Reading only `document["on"]` finds nothing, in every workflow ever
    written, and reports every repository as merging without a gate.
    """
    raw = document.get("on", document.get(True))
    if isinstance(raw, dict):
        return tuple(str(key) for key in raw)
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    return (str(raw),) if isinstance(raw, str) else ()


def _commands_in(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) in _STEP_KEYS:
                found.extend(_as_strings(value))
            else:
                found.extend(_commands_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_commands_in(item))
    return found


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _test_command(commands: list[str]) -> str:
    """The line that runs the tests, as written, or empty if none does."""
    for command in commands:
        for line in command.splitlines():
            stripped = line.strip()
            if any(name in stripped for name in TEST_COMMANDS):
                return stripped
    return ""


def _yaml_mapping(text: str) -> dict[Any, Any] | None:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else None


# -- web servers -----------------------------------------------------------

# A worker count and a timeout, which is what a pool size and a client timeout
# are only right or wrong relative to.
NGINX_DIRECTIVES = (
    "worker_processes",
    "worker_connections",
    "keepalive_timeout",
    "proxy_read_timeout",
    "proxy_connect_timeout",
    "proxy_send_timeout",
    "send_timeout",
    "client_max_body_size",
)

# What only a web server's configuration says. A Postgres `primary.conf` has a
# `listen_addresses` and a `max_connections`, so a sniff for anything as
# generic as `listen` would call every .conf in the repository nginx.
NGINX_MARKERS = re.compile(
    r"(?:^|[;{])\s*(?:upstream|location|proxy_pass|fastcgi_pass|server_name"
    r"|worker_processes|worker_connections|keepalive_timeout)\b",
    re.MULTILINE,
)

GUNICORN_SETTINGS = (
    "workers",
    "threads",
    "worker_class",
    "worker_connections",
    "timeout",
    "graceful_timeout",
    "keepalive",
    "max_requests",
    "backlog",
)


def _webserver(name: str, text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Worker counts and timeouts, in whichever grammar this file uses.

    Nothing is extracted from a Caddyfile or a uvicorn.json. Uvicorn's worker
    count is a command-line flag in practice, and the survey already keeps the
    command verbatim for exactly that reason.
    """
    if name.endswith((".py", ".ini")):
        return {key: value for key in GUNICORN_SETTINGS if (value := _assignment(text, key))}, ()
    if name.endswith(".conf"):
        return {key: value for key in NGINX_DIRECTIVES if (value := _directive(text, key))}, ()
    return {}, ()


def _directive(text: str, name: str) -> str:
    """`worker_processes 4;` as nginx and its several imitators write it.

    Every distinct value rather than the first, because a directive is scoped
    to the block it sits in and nothing here reads blocks. An upstream's
    `keepalive_timeout` and a server's are different numbers under one name,
    and reporting the first silently answers a question about the second.
    """
    seen: list[str] = []
    for match in re.finditer(rf"(?:^|[;{{])\s*{re.escape(name)}\s+([^;\n]+);", text, re.MULTILINE):
        value = match.group(1).strip()
        if value not in seen:
            seen.append(value)
    return ", ".join(seen)


def _assignment(text: str, name: str) -> str:
    """`workers = 2` as a gunicorn config and a uwsgi ini both write it.

    The last assignment, because a gunicorn config is executed rather than
    parsed. A `workers` set once at the top and again below a condition runs
    at the second value, and reporting the first describes a process that
    never existed.
    """
    found = re.findall(rf"^\s*{re.escape(name)}\s*=\s*([^#\n]+)", text, re.MULTILINE)
    return str(found[-1]).strip().strip("\"'") if found else ""


# -- manifests, lockfiles, procfiles and examples --------------------------


def _manifest(
    name: str, relative: str, beside: dict[str, set[str]]
) -> tuple[dict[str, str], tuple[str, ...]]:
    facts = {"ecosystem": MANIFEST_ECOSYSTEMS[name]}
    expected = LOCKS_FOR.get(name, ())
    if not expected:
        return facts, ()

    # In the same directory, because that is where the tool that reads the
    # manifest looks. A lockfile at the repository root does not pin a
    # workspace member's dependencies.
    neighbours = beside.get(relative.rpartition("/")[0], set())
    present = [lock for lock in expected if lock in neighbours]
    if present:
        facts["lockfile"] = present[0]
        return facts, ()
    return facts, ("lockfile",)


def _procfile(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Process type to the command, verbatim.

    A worker's concurrency ceiling and a web process's worker count live in
    this line and nowhere else in the repository, exactly as they do in a
    compose command.
    """
    facts: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        process, separator, command = stripped.partition(":")
        if separator and command.strip() and len(facts) < MAX_PROCESSES:
            facts[process.strip()] = command.strip()
    return facts, ()


def _env_example(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """The variable names an example file declares. Never the values.

    This file is committed, so by convention it holds placeholders. Convention
    is what should be in it rather than what is, and a name is the whole of
    what a reviewer needs: a variable the code reads and this file omits is
    the defect, and no value is required to see it.
    """
    names: list[str] = []
    for line in text.splitlines():
        # Commented lines count. An optional variable is conventionally
        # declared as `# SENTRY_DSN=`, and reading only uncommented lines found
        # five of the eleven variables this project's own example documents --
        # so every optional variable would have looked undeclared.
        declaration = line.strip().removeprefix("#").strip().removeprefix("export ")
        candidate, separator, _ = declaration.partition("=")
        # The `=` is what separates a declaration from prose. Without it a bare
        # `# TODO` is indistinguishable from a variable name.
        if separator and _ENV_NAME.match(candidate.strip()):
            name = candidate.strip()
            if name not in names:
                names.append(name)
    return ({"variables": ", ".join(names[:MAX_ENV_NAMES])} if names else {}), ()
