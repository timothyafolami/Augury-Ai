"""What the deployment declares, checked without asking a model.

A deployment defect is not in any source file. `FROM python:3.13-slim` with no
`USER` is two correct lines that hand a container escape uid 0, and
`--workers $(nproc)` is one correct line that asks for 17 processes under a
2-CPU quota. No per-module review reaches either, because the module is right;
what is wrong is the machine it is told to run on.

Every check here is arithmetic or a grep over a declaration, so none of it
costs a model call and none of it can be hallucinated. That is the point: a
model asked how many backends `replicas x workers x (pool_size + max_overflow)`
opens will answer with a plausible number rather than that one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from augury.core.artifacts.checks import Artifact, deployment_findings, is_secret_env
from augury.core.artifacts.reader import read_artifacts
from augury.core.schema.model import SchemaFinding


@dataclass(frozen=True)
class Stub:
    """One artefact carrying its own text."""

    kind: str
    path: str
    text: str


@dataclass(frozen=True)
class Listed:
    """One artefact in the reader's own shape: classified, and not carried.

    The reader keeps per-kind facts rather than contents, because the inventory
    is sent with a review and the files are not. These rules need the file as
    written, so they open it themselves.
    """

    kind: str
    path: str


class Landmine:
    """An artefact whose contents fail the test if anything reads them.

    A .env holds live credentials for the repository under review. The rule is
    not "redact it later", it is "never open it", and the only way to pin that
    is to make opening it an error.
    """

    kind = "dotenv"

    def __init__(self, path: str) -> None:
        self.path = path

    @property
    def text(self) -> str:
        raise AssertionError(f"{self.path} was read")


def _rules(*artifacts: Artifact) -> list[str]:
    return [f.rule for f in deployment_findings(artifacts)]


def _one(rule: str, *artifacts: Artifact) -> SchemaFinding:
    matching = [f for f in deployment_findings(artifacts) if f.rule == rule]
    assert len(matching) == 1, f"expected one {rule}, got {[f.rule for f in matching]}"
    return matching[0]


# -- container-runs-as-root ------------------------------------------------

ROOT_DOCKERFILE = """\
FROM python:3.13-slim
WORKDIR /srv
COPY . /srv
HEALTHCHECK CMD curl -f http://localhost:8000/healthz
CMD ["uvicorn", "main:app", "--workers", "2"]
"""


def test_a_dockerfile_with_no_user_instruction_is_reported() -> None:
    """No USER means uid 0, so a container escape is a root escape."""
    assert "container-runs-as-root" in _rules(Stub("dockerfile", "Dockerfile", ROOT_DOCKERFILE))


def test_the_root_finding_names_uid_zero() -> None:
    finding = _one("container-runs-as-root", Stub("dockerfile", "Dockerfile", ROOT_DOCKERFILE))
    assert "uid 0" in finding.detail
    assert "USER" in finding.remediation


def test_a_dockerfile_that_drops_to_a_user_is_fine() -> None:
    body = ROOT_DOCKERFILE.replace("CMD [", "USER app\nCMD [")
    assert "container-runs-as-root" not in _rules(Stub("dockerfile", "Dockerfile", body))


def test_user_root_written_out_is_still_root() -> None:
    """`USER root` is a decision rather than an oversight, and still uid 0."""
    body = ROOT_DOCKERFILE.replace("CMD [", "USER root\nCMD [")
    assert "container-runs-as-root" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_only_the_final_stage_decides_who_the_process_runs_as() -> None:
    """The builder stage is discarded. A USER in it protects nothing."""
    body = (
        "FROM python:3.13-slim AS builder\n"
        "USER app\n"
        "RUN pip install -r requirements.txt\n"
        "\n"
        "FROM python:3.13-slim\n"
        "COPY --from=builder /srv /srv\n"
        'CMD ["uvicorn", "main:app"]\n'
    )
    assert "container-runs-as-root" in _rules(Stub("dockerfile", "Dockerfile", body))


# -- no-memory-limit -------------------------------------------------------

COMPOSE_NO_LIMITS = """\
services:
  api:
    build: .
    ports:
      - "8000:8000"
    command: uvicorn main:app --workers 2
"""


def test_a_service_with_no_memory_limit_is_reported() -> None:
    assert "no-memory-limit" in _rules(Stub("compose", "docker-compose.yml", COMPOSE_NO_LIMITS))


def test_the_memory_finding_derives_exit_137() -> None:
    """128 + SIGKILL's 9. A reader who has the derivation does not need the table."""
    finding = _one("no-memory-limit", Stub("compose", "docker-compose.yml", COMPOSE_NO_LIMITS))
    detail = finding.detail
    assert "137" in detail
    assert "128" in detail and "9" in detail


def test_a_mem_limit_satisfies_it() -> None:
    body = COMPOSE_NO_LIMITS.replace("    build: .", "    build: .\n    mem_limit: 1g")
    assert "no-memory-limit" not in _rules(Stub("compose", "docker-compose.yml", body))


def test_a_deploy_resources_limit_satisfies_it() -> None:
    """Compose v3 spells the same cgroup file a different way."""
    body = COMPOSE_NO_LIMITS + (
        "    deploy:\n      resources:\n        limits:\n          memory: 512M\n"
    )
    assert "no-memory-limit" not in _rules(Stub("compose", "docker-compose.yml", body))


# -- workers-ignore-the-cpu-quota -----------------------------------------


def test_the_most_copied_formula_in_python_deployment_guides_is_reported() -> None:
    body = (
        "FROM python:3.13-slim\nUSER app\n"
        'CMD ["sh", "-c", "gunicorn -w $((2 * $(nproc) + 1)) app"]\n'
    )
    assert "workers-ignore-the-cpu-quota" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_the_quota_finding_carries_the_seventeen() -> None:
    """2 * 8 + 1 on an eight-core host, under a two-CPU quota."""
    body = 'FROM python:3.13-slim\nCMD ["sh", "-c", "gunicorn -w $((2 * $(nproc) + 1)) app"]\n'
    finding = _one("workers-ignore-the-cpu-quota", Stub("dockerfile", "Dockerfile", body))
    assert "17" in finding.detail


def test_os_cpu_count_in_a_procfile_is_reported() -> None:
    body = "web: uvicorn main:app --workers $(python -c 'import os; print(os.cpu_count())')\n"
    assert "workers-ignore-the-cpu-quota" in _rules(Stub("procfile", "Procfile", body))


def test_nproc_in_a_compose_command_is_reported() -> None:
    body = COMPOSE_NO_LIMITS.replace("--workers 2", "--workers $(nproc)")
    assert "workers-ignore-the-cpu-quota" in _rules(Stub("compose", "docker-compose.yml", body))


def test_a_worker_count_taken_from_the_environment_is_fine() -> None:
    """The deployment already knows the quota. Making it say so is the fix."""
    body = COMPOSE_NO_LIMITS.replace("--workers 2", "--workers ${WORKERS}")
    assert "workers-ignore-the-cpu-quota" not in _rules(Stub("compose", "docker-compose.yml", body))


# -- quota-without-replicas-arithmetic ------------------------------------

COMPOSE_OVERSUBSCRIBED = """\
services:
  api:
    build: .
    mem_limit: 1g
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
    command: uvicorn main:app --workers 4
    environment:
      POOL_SIZE: 10
      MAX_OVERFLOW: 10
    deploy:
      replicas: 3
  db:
    image: postgres:18.6
    mem_limit: 1g
    command: postgres -c max_connections=100
"""


def test_the_connection_product_is_reported_when_every_part_is_visible() -> None:
    """3 x 4 x (10 + 10) = 240 against a budget of 97."""
    finding = _one(
        "quota-without-replicas-arithmetic",
        Stub("compose", "docker-compose.yml", COMPOSE_OVERSUBSCRIBED),
    )
    detail = finding.detail
    assert "240" in detail
    assert "97" in detail, "max_connections 100 less the 3 Postgres reserves for superusers"


def test_a_product_that_fits_the_budget_is_not_reported() -> None:
    body = COMPOSE_OVERSUBSCRIBED.replace("replicas: 3", "replicas: 1").replace(
        "--workers 4", "--workers 2"
    )
    assert "quota-without-replicas-arithmetic" not in _rules(
        Stub("compose", "docker-compose.yml", body)
    )


def test_nothing_is_reported_when_the_pool_size_is_not_visible() -> None:
    """A product with a guessed factor in it is a fabricated number."""
    body = COMPOSE_OVERSUBSCRIBED.replace("      POOL_SIZE: 10\n", "").replace(
        "      MAX_OVERFLOW: 10\n", ""
    )
    assert "quota-without-replicas-arithmetic" not in _rules(
        Stub("compose", "docker-compose.yml", body)
    )


# -- no-healthcheck --------------------------------------------------------


def test_a_service_taking_traffic_with_no_probe_is_reported() -> None:
    assert "no-healthcheck" in _rules(Stub("compose", "docker-compose.yml", COMPOSE_NO_LIMITS))


def test_a_service_with_a_healthcheck_is_fine() -> None:
    assert "no-healthcheck" not in _rules(
        Stub("compose", "docker-compose.yml", COMPOSE_OVERSUBSCRIBED)
    )


def test_a_dockerfile_with_no_healthcheck_and_no_compose_is_reported() -> None:
    body = 'FROM python:3.13-slim\nUSER app\nCMD ["uvicorn", "main:app"]\n'
    assert "no-healthcheck" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_the_dockerfile_is_not_reported_twice_alongside_a_compose_file() -> None:
    """A repository with a compose file declares its probes there."""
    rules = _rules(
        Stub("dockerfile", "Dockerfile", 'FROM python:3.13-slim\nCMD ["uvicorn", "main:app"]\n'),
        Stub("compose", "docker-compose.yml", COMPOSE_OVERSUBSCRIBED),
    )
    assert rules.count("no-healthcheck") == 0


# -- latest-tag ------------------------------------------------------------


def test_an_explicit_latest_tag_is_reported() -> None:
    body = 'FROM python:latest\nUSER app\nHEALTHCHECK CMD true\nCMD ["true"]\n'
    assert "latest-tag" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_an_untagged_image_is_latest_by_default() -> None:
    body = 'FROM python\nUSER app\nHEALTHCHECK CMD true\nCMD ["true"]\n'
    assert "latest-tag" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_a_pinned_tag_is_fine() -> None:
    assert "latest-tag" not in _rules(Stub("dockerfile", "Dockerfile", ROOT_DOCKERFILE))


def test_a_digest_is_fine() -> None:
    """The digest pins the exact bytes, whatever tag sits beside it."""
    for reference in ("python@sha256:0123456789abcdef", "python:latest@sha256:0123456789abcdef"):
        body = f"FROM {reference}\nUSER app\nHEALTHCHECK CMD true\n"
        assert "latest-tag" not in _rules(Stub("dockerfile", "Dockerfile", body)), reference


def test_a_registry_port_is_not_read_as_a_tag() -> None:
    """`registry.local:5000/app` is untagged, not tagged `5000/app`."""
    body = "FROM registry.local:5000/app\nUSER app\nHEALTHCHECK CMD true\n"
    assert "latest-tag" in _rules(Stub("dockerfile", "Dockerfile", body))


def test_a_stage_alias_is_not_an_image() -> None:
    """`FROM builder` names an earlier stage, and no registry is consulted."""
    body = (
        "FROM python:3.13-slim AS builder\n"
        "RUN pip install .\n"
        "FROM builder\n"
        "USER app\n"
        "HEALTHCHECK CMD true\n"
    )
    assert "latest-tag" not in _rules(Stub("dockerfile", "Dockerfile", body))


def test_a_build_arg_resolves_to_its_default() -> None:
    body = (
        "ARG PYTHON_IMAGE=python:3.13-slim\nFROM ${PYTHON_IMAGE}\nUSER app\nHEALTHCHECK CMD true\n"
    )
    assert "latest-tag" not in _rules(Stub("dockerfile", "Dockerfile", body))


def test_a_latest_image_in_a_compose_file_is_reported() -> None:
    body = COMPOSE_OVERSUBSCRIBED.replace("postgres:18.6", "postgres:latest")
    assert "latest-tag" in _rules(Stub("compose", "docker-compose.yml", body))


# -- lockfile-missing ------------------------------------------------------


def test_a_manifest_with_no_lockfile_is_reported() -> None:
    assert "lockfile-missing" in _rules(Stub("manifest", "pyproject.toml", "[project]\n"))


def test_a_manifest_beside_its_lockfile_is_fine() -> None:
    assert "lockfile-missing" not in _rules(
        Stub("manifest", "pyproject.toml", "[project]\n"),
        Stub("lockfile", "uv.lock", ""),
    )


def test_the_lockfile_must_be_the_one_that_ecosystem_writes() -> None:
    """A Cargo.lock does not lock a package.json."""
    assert "lockfile-missing" in _rules(
        Stub("manifest", "package.json", "{}"),
        Stub("lockfile", "Cargo.lock", ""),
    )


def test_a_lockfile_in_another_directory_does_not_count() -> None:
    assert "lockfile-missing" in _rules(
        Stub("manifest", "backend/package.json", "{}"),
        Stub("lockfile", "frontend/package-lock.json", ""),
    )


def test_requirements_txt_is_not_reported_as_missing_a_lock() -> None:
    """pip has no lockfile format to be missing, and the unpinned entries in
    one are already reported by the dependency checks."""
    assert "lockfile-missing" not in _rules(Stub("manifest", "requirements.txt", "fastapi\n"))


# -- ci-does-not-gate ------------------------------------------------------

WORKFLOW_PUSH_ONLY = """\
name: ci
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make check
"""


def test_a_workflow_that_runs_tests_only_after_the_merge_is_reported() -> None:
    assert "ci-does-not-gate" in _rules(
        Stub("workflow", ".github/workflows/ci.yml", WORKFLOW_PUSH_ONLY)
    )


def test_yaml_reading_on_as_a_boolean_does_not_hide_the_trigger() -> None:
    """YAML 1.1 resolves a bare `on` key to True, which is how a workflow with
    a pull_request trigger gets reported as having none."""
    body = WORKFLOW_PUSH_ONLY.replace("  push:\n    branches: [main]\n", "  pull_request:\n")
    assert "ci-does-not-gate" not in _rules(Stub("workflow", ".github/workflows/ci.yml", body))


def test_the_gate_finding_points_at_the_trigger_block_not_at_runs_on() -> None:
    """`runs-on:` carries the same three characters, and a workflow may declare
    its jobs above its triggers."""
    body = (
        "name: ci\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: pytest -q\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
    )
    finding = _one("ci-does-not-gate", Stub("workflow", ".github/workflows/ci.yml", body))
    assert finding.line == 7


def test_a_step_allowed_to_fail_does_not_gate() -> None:
    body = WORKFLOW_PUSH_ONLY.replace("  push:\n    branches: [main]\n", "  pull_request:\n")
    body = body.replace(
        "      - run: make check",
        "      - run: make check\n        continue-on-error: true",
    )
    assert "ci-does-not-gate" in _rules(Stub("workflow", ".github/workflows/ci.yml", body))


def test_a_test_command_swallowed_by_or_true_does_not_gate() -> None:
    body = WORKFLOW_PUSH_ONLY.replace("  push:\n    branches: [main]\n", "  pull_request:\n")
    body = body.replace("make check", "pytest -q || true")
    assert "ci-does-not-gate" in _rules(Stub("workflow", ".github/workflows/ci.yml", body))


def test_a_workflow_that_runs_no_tests_is_not_a_gate_that_is_missing() -> None:
    body = WORKFLOW_PUSH_ONLY.replace("      - run: make check", "      - run: ./deploy.sh")
    assert "ci-does-not-gate" not in _rules(Stub("workflow", ".github/workflows/ci.yml", body))


def test_one_workflow_produces_at_most_one_gate_finding() -> None:
    """Push-only and swallowed are two spellings of the same defect."""
    body = WORKFLOW_PUSH_ONLY.replace("make check", "pytest -q || true")
    assert _rules(Stub("workflow", ".github/workflows/ci.yml", body)).count("ci-does-not-gate") == 1


# -- the shape of every finding -------------------------------------------

EVERYTHING = (
    Stub("dockerfile", "Dockerfile", 'FROM python\nCMD ["sh", "-c", "app -w $(nproc)"]\n'),
    Stub("compose", "docker-compose.yml", COMPOSE_OVERSUBSCRIBED),
    Stub("manifest", "package.json", "{}"),
    Stub("workflow", ".github/workflows/ci.yml", WORKFLOW_PUSH_ONLY),
)


def test_every_finding_names_a_file_and_a_line_that_exists() -> None:
    by_path = {a.path: a.text.splitlines() for a in EVERYTHING}
    for finding in deployment_findings(EVERYTHING):
        assert finding.path in by_path, finding.rule
        assert 1 <= finding.line <= len(by_path[finding.path]), f"{finding.rule} {finding.line}"


def test_every_remediation_is_a_change_rather_than_advice() -> None:
    advice = ("consider", "you should", "it is recommended", "make sure", "be aware")
    for finding in deployment_findings(EVERYTHING):
        opening = finding.remediation.lower()
        assert not any(opening.startswith(word) for word in advice), finding.remediation
        assert len(finding.remediation) > 20, finding.rule


def test_the_same_inventory_gives_the_same_answer_every_run() -> None:
    once = deployment_findings(EVERYTHING)
    assert once == deployment_findings(EVERYTHING)


def test_the_order_the_reader_walked_the_repository_does_not_change_the_answer() -> None:
    """Determinism has to survive a reader that sorts its inventory differently."""
    assert deployment_findings(EVERYTHING) == deployment_findings(tuple(reversed(EVERYTHING)))


# -- artefacts that carry no text -----------------------------------------


def test_an_artefact_without_text_is_read_from_the_root(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(ROOT_DOCKERFILE)
    listed = (Listed("dockerfile", "Dockerfile"),)

    assert "container-runs-as-root" in [f.rule for f in deployment_findings(listed, root=tmp_path)]


def test_an_artefact_without_text_and_without_a_root_reports_nothing(tmp_path: Path) -> None:
    """Knowing less is the honest answer. Guessing at the contents is not."""
    (tmp_path / "Dockerfile").write_text(ROOT_DOCKERFILE)

    assert deployment_findings((Listed("dockerfile", "Dockerfile"),)) == ()


def test_a_file_the_root_does_not_hold_reports_nothing(tmp_path: Path) -> None:
    assert deployment_findings((Listed("dockerfile", "Dockerfile"),), root=tmp_path) == ()


def test_the_real_reader_drives_these_rules(tmp_path: Path) -> None:
    """The two modules have to fit, and only an inventory proves that they do."""
    (tmp_path / "Dockerfile").write_text('FROM python\nCMD ["uvicorn", "main:app"]\n')
    (tmp_path / "docker-compose.yml").write_text(COMPOSE_NO_LIMITS)
    (tmp_path / "package.json").write_text("{}")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(WORKFLOW_PUSH_ONLY)

    inventory = read_artifacts(tmp_path)
    rules = {f.rule for f in deployment_findings(inventory.artifacts, root=tmp_path)}

    assert {
        "container-runs-as-root",
        "latest-tag",
        "no-memory-limit",
        "no-healthcheck",
        "lockfile-missing",
        "ci-does-not-gate",
    } <= rules


# -- the .env rule ---------------------------------------------------------


def test_a_dotenv_is_never_read() -> None:
    """It holds live credentials for the repository under review."""
    assert deployment_findings((Landmine(".env"),)) == ()


def test_a_dotenv_anywhere_in_the_tree_is_never_read() -> None:
    for path in (".env", "backend/.env", ".env.local", ".env.production", "app/.env.prod"):
        assert deployment_findings((Landmine(path),)) == (), path


def test_a_dotenv_does_not_stop_the_other_artefacts_being_checked() -> None:
    """Refusing one file is not a reason to report nothing."""
    rules = _rules(Landmine(".env"), Stub("dockerfile", "Dockerfile", ROOT_DOCKERFILE))
    assert "container-runs-as-root" in rules


def test_a_dotenv_on_disk_is_not_opened_even_when_a_root_is_given(tmp_path: Path) -> None:
    """The refusal has to survive the path that reads from the filesystem."""
    (tmp_path / ".env").write_text("DATABASE_URL=postgres://live:s3cret-4b71@prod/db\n")
    (tmp_path / "Dockerfile").write_text(ROOT_DOCKERFILE)
    listed = (Listed("dotenv", ".env"), Listed("dockerfile", "Dockerfile"))

    found = deployment_findings(listed, root=tmp_path)

    assert [f.rule for f in found].count("container-runs-as-root") == 1
    assert not any(f.path == ".env" for f in found)
    assert "s3cret-4b71" not in " ".join(f.detail + f.remediation for f in found)


def test_the_reader_refuses_to_inventory_a_dotenv_at_all(tmp_path: Path) -> None:
    """Two independent refusals. This one pins the reader's, so that a caller
    using the inventory never reaches these rules with a .env in hand."""
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk-live-4b71\n")
    (tmp_path / ".env.example").write_text("GROQ_API_KEY=\n")

    paths = {artifact.path for artifact in read_artifacts(tmp_path).artifacts}

    assert ".env" not in paths
    assert ".env.example" in paths


def test_the_committed_example_files_are_safe_to_read() -> None:
    """.env.example and .env.sample are committed and hold no secret."""
    for path in (".env.example", ".env.sample", "backend/.env.example"):
        assert not is_secret_env(path), path


def test_every_other_dotenv_spelling_is_a_secret() -> None:
    for path in (".env", ".env.local", ".env.prod", "svc/.env", ".env.production.local"):
        assert is_secret_env(path), path
