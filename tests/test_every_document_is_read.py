"""Everything a repository ships that is not source code.

The map reads .py, .ts, .go, .rs, .java and .cpp. A large share of production
defects is in none of them. The container that runs as root, the deployment
with a request and no limit, the workflow that merges without running the
tests, the manifest with no lockfile beside it: every one of those is a defect,
and every one is invisible to a reviewer that only opens source files.

Layer 1e of the practice lab is the case in point. Seven topics about what a
process is allowed to do inside a container, and zero of them are covered,
because the facts live in cpu.max, memory.max and a Dockerfile rather than in
any module.

This reads and classifies. It does not parse each format deeply, and it does
not judge. An inventory of what exists and the few facts that matter per kind
is what a specialist needs to ask the right question; the answer costs a call
and belongs elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.artifacts import ArtifactKind, holds_live_credentials, read_artifacts

# A value that exists nowhere but a .env. If it appears anywhere in the
# inventory then a live credential has reached something that is printed,
# cached, committed as a recording and sent to a model.
LIVE_SECRET = "sk-live-2f9c-never-read-this"

DOCKERFILE = """\
FROM python:3.12 AS builder
COPY requirements.txt /tmp/requirements.txt
RUN pip install --prefix=/install -r /tmp/requirements.txt

FROM python:3.12-slim
COPY --from=builder /install /usr/local
COPY . /app
WORKDIR /app
CMD ["gunicorn", "app:app"]
"""

COMPOSE = """\
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
  redis:
    image: redis:7-alpine
"""

DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: api
          image: ghcr.io/acme/api:1.4.0
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
          readinessProbe:
            httpGet: { path: /healthz, port: 8000 }
"""

HPA = """\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api
spec:
  minReplicas: 2
  maxReplicas: 10
  scaleTargetRef:
    kind: Deployment
    name: api
"""

CI = """\
name: ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make check
"""

RELEASE = """\
name: release
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - run: docker build -t acme/api .
"""

NGINX = """\
worker_processes 4;
events {
    worker_connections 1024;
}
http {
    keepalive_timeout 65;
    upstream api { server api:8000; }
    server {
        location / {
            proxy_pass http://api;
            proxy_read_timeout 30s;
        }
    }
}
"""

GUNICORN = """\
workers = 2
threads = 4
timeout = 30
worker_class = "uvicorn.workers.UvicornWorker"
"""

PROCFILE = """\
web: gunicorn app:app --workers 2
worker: celery -A app.tasks worker --concurrency=1
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository that ships everything except a review of any of it."""
    write = _writer(tmp_path)

    write("Dockerfile", DOCKERFILE)
    write("docker-compose.yml", COMPOSE)
    write("k8s/deployment.yaml", DEPLOYMENT)
    write("k8s/hpa.yaml", HPA)
    write(".github/workflows/ci.yml", CI)
    write(".github/workflows/release.yml", RELEASE)
    write("deploy/nginx.conf", NGINX)
    write("gunicorn.conf.py", GUNICORN)
    write("Procfile", PROCFILE)
    write("infra/main.tf", 'resource "aws_ecs_service" "api" {}\n')

    # A manifest with its lockfile beside it, and one without.
    write("pyproject.toml", '[project]\nname = "api"\n')
    write("uv.lock", "version = 1\n")
    write("frontend/package.json", '{"name": "web"}\n')

    # Committed and safe. Placeholder values, so no secret is in it. Six of the
    # eleven variables this project's own .env.example documents are commented
    # out, which is how an optional variable is conventionally declared.
    write(
        ".env.example",
        "# Copy to .env and fill in.\n"
        "# TODO\n"
        "OPENAI_API_KEY=replace-me-4b71\n"
        "DATABASE_URL=postgres://localhost\n"
        "# Optional, unset by default.\n"
        "# SENTRY_DSN=\n",
    )

    # Live credentials. Never read, never classified, never inventoried.
    write(".env", f"OPENAI_API_KEY={LIVE_SECRET}\n")
    write(".env.production", f"DATABASE_URL=postgres://user:{LIVE_SECRET}@prod/db\n")
    write(".github/workflows/.env.staging", f"OPENAI_API_KEY={LIVE_SECRET}\n")

    # Somebody else's code. The mapper already refuses to walk into it.
    write("node_modules/leftpad/Dockerfile", "FROM node:20\nUSER node\n")

    # Source. The map reads this; the inventory has no business with it.
    write("backend/app.py", "import fastapi\n")
    return tmp_path


def _writer(root: Path):  # type: ignore[no-untyped-def]
    def write(relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    return write


def _paths(repo: Path, kind: ArtifactKind) -> set[str]:
    return {artifact.path for artifact in read_artifacts(repo).of(kind)}


def _one(repo: Path, kind: ArtifactKind, path: str):  # type: ignore[no-untyped-def]
    return next(a for a in read_artifacts(repo).of(kind) if a.path == path)


# -- the security rule, first because it outranks every other one ----------


def test_a_dotenv_is_never_read_never_classified_and_never_inventoried(repo: Path) -> None:
    """It holds live credentials for the repository under review.

    An inventory is printed, cached, committed as a recording and sent to a
    model. A key that reaches any of those is a key that has to be rotated.

    The fixture puts one of them under .github/workflows, where the CI
    classifier would otherwise claim it. That is the case that says the guard
    runs during the walk rather than after something has decided what kind of
    file this is.
    """
    inventory = read_artifacts(repo)
    names = {artifact.path.rpartition("/")[2] for artifact in inventory.artifacts}

    assert LIVE_SECRET not in inventory.model_dump_json()
    assert names.isdisjoint({".env", ".env.production", ".env.staging"})


@pytest.mark.parametrize(
    "name", [".env", ".env.local", ".env.staging", ".env.production", ".envrc", ".ENV"]
)
def test_every_spelling_of_a_live_dotenv_is_refused(name: str) -> None:
    """The allowlist is the safe names. Everything else beginning .env is not.

    Asserted on the guard itself and not only on the inventory, because today
    nothing classifies a `.env.local` and so an inventory stays clean whether
    the guard works or not. The next kind added would silently undo that.
    """
    assert holds_live_credentials(name) is True


@pytest.mark.parametrize("name", [".env.example", ".env.sample", ".env.template"])
def test_a_committed_example_is_not_refused(name: str) -> None:
    assert holds_live_credentials(name) is False


def test_an_example_env_is_read_because_it_is_committed_and_holds_nothing(repo: Path) -> None:
    """A variable the code reads and the example omits is a defect in itself."""
    example = _one(repo, ArtifactKind.ENV_EXAMPLE, ".env.example")

    assert "OPENAI_API_KEY" in example.facts["variables"]
    assert "DATABASE_URL" in example.facts["variables"]


def test_a_commented_out_variable_is_still_a_declared_variable(repo: Path) -> None:
    """Run against this project's own .env.example, reading only uncommented
    lines found five of its eleven variables. A commented `# SENTRY_DSN=` is
    how an optional variable is documented, and dropping it makes every
    optional variable look undeclared."""
    assert "SENTRY_DSN" in _one(repo, ArtifactKind.ENV_EXAMPLE, ".env.example").facts["variables"]


def test_a_comment_that_is_prose_does_not_become_a_variable(repo: Path) -> None:
    """A bare `# TODO` declares nothing. A single word in a comment looks
    exactly like a variable name until you require the `=` that makes it a
    declaration."""
    variables = _one(repo, ArtifactKind.ENV_EXAMPLE, ".env.example").facts["variables"]

    assert "TODO" not in variables


def test_even_an_example_env_keeps_names_and_never_values(repo: Path) -> None:
    """It is committed, so it should hold no secret. Should is not does."""
    assert "replace-me-4b71" not in read_artifacts(repo).model_dump_json()


# -- the container, which is where layer 1e lives --------------------------


def test_a_dockerfile_names_the_image_that_actually_ships(repo: Path) -> None:
    """The final stage. A builder's base is not what runs in production."""
    assert _one(repo, ArtifactKind.DOCKERFILE, "Dockerfile").facts["base_image"] == (
        "python:3.12-slim"
    )


def test_a_dockerfile_that_sets_no_user_says_so(repo: Path) -> None:
    """No USER is a fact about the file, not a guess about the process.

    Recorded as an absence rather than as `user: root`, because what the
    process actually runs as is decided by the base image and this file does
    not say.
    """
    dockerfile = _one(repo, ArtifactKind.DOCKERFILE, "Dockerfile")

    assert "USER" in dockerfile.absent
    assert "user" not in dockerfile.facts


def test_a_dockerfile_keeps_what_it_copies_in(repo: Path) -> None:
    """`COPY . /app` is how a .env and a .git reach a published image."""
    assert ". /app" in _one(repo, ArtifactKind.DOCKERFILE, "Dockerfile").facts["copies"]


def test_a_dockerfile_with_no_healthcheck_says_so(repo: Path) -> None:
    assert "HEALTHCHECK" in _one(repo, ArtifactKind.DOCKERFILE, "Dockerfile").absent


# -- compose, which somebody else already reads ----------------------------


def test_a_compose_file_is_recorded_and_points_at_the_surveyor(repo: Path) -> None:
    """The survey parses it into services and scope. Doing it twice would give
    two answers to one question and no way to tell which is stale."""
    compose = _one(repo, ArtifactKind.COMPOSE, "docker-compose.yml")

    assert "Surveyor" in compose.facts["read_by"]
    assert "redis" not in compose.model_dump_json()


# -- kubernetes ------------------------------------------------------------


def test_a_deployment_reports_its_replicas_and_what_it_asks_for(repo: Path) -> None:
    deployment = _one(repo, ArtifactKind.KUBERNETES, "k8s/deployment.yaml")

    assert deployment.facts["kind"] == "Deployment"
    assert deployment.facts["replicas"] == "3"
    assert "memory=128Mi" in deployment.facts["requests"]


def test_a_deployment_with_a_request_and_no_limit_says_which_is_missing(repo: Path) -> None:
    """This is the whole of layer 1e in one line. A container with no memory
    limit is not bounded by the manifest; it is bounded by the node, and it
    finds that out by being killed."""
    deployment = _one(repo, ArtifactKind.KUBERNETES, "k8s/deployment.yaml")

    assert "resources.limits" in deployment.absent
    assert "resources.requests" not in deployment.absent


def test_a_deployment_reports_which_probes_it_has_and_which_it_lacks(repo: Path) -> None:
    deployment = _one(repo, ArtifactKind.KUBERNETES, "k8s/deployment.yaml")

    assert deployment.facts["probes"] == "readiness"
    assert "livenessProbe" in deployment.absent


def test_an_autoscaler_reports_the_range_it_may_scale_over(repo: Path) -> None:
    hpa = _one(repo, ArtifactKind.KUBERNETES, "k8s/hpa.yaml")

    assert hpa.facts["min_replicas"] == "2"
    assert hpa.facts["max_replicas"] == "10"


def test_a_yaml_that_is_not_kubernetes_is_not_called_kubernetes(repo: Path) -> None:
    """A compose file and a workflow are both YAML and neither is a manifest."""
    assert _paths(repo, ArtifactKind.KUBERNETES) == {"k8s/deployment.yaml", "k8s/hpa.yaml"}


# -- continuous integration ------------------------------------------------


def test_every_workflow_is_listed(repo: Path) -> None:
    assert _paths(repo, ArtifactKind.CI) == {
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    }


def test_a_workflow_reports_the_command_it_runs_the_tests_with(repo: Path) -> None:
    workflow = _one(repo, ArtifactKind.CI, ".github/workflows/ci.yml")

    assert workflow.facts["tests"] == "make check"
    assert "pull_request" in workflow.facts["triggers"]


def test_a_workflow_that_runs_no_tests_says_so(repo: Path) -> None:
    assert "tests" in _one(repo, ArtifactKind.CI, ".github/workflows/release.yml").absent


def test_the_inventory_answers_whether_tests_gate_the_merge(repo: Path) -> None:
    """One workflow that runs on pull_request and runs the tests is enough."""
    assert read_artifacts(repo).tests_gate_the_merge is True


def test_a_repository_whose_tests_run_only_after_the_merge_does_not_gate(
    tmp_path: Path,
) -> None:
    """Tests on push to main find the defect once it is everyone's."""
    path = tmp_path / ".github" / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "on:\n  push:\n    branches: [main]\njobs:\n  t:\n    steps:\n      - run: pytest -q\n"
    )

    assert read_artifacts(tmp_path).tests_gate_the_merge is False


# -- the web server, where a worker count meets a timeout ------------------


def test_nginx_reports_its_worker_counts_and_timeouts(repo: Path) -> None:
    nginx = _one(repo, ArtifactKind.WEBSERVER, "deploy/nginx.conf")

    assert nginx.facts["worker_processes"] == "4"
    assert nginx.facts["worker_connections"] == "1024"
    assert nginx.facts["proxy_read_timeout"] == "30s"


def test_a_web_server_config_is_found_by_what_it_says_not_by_what_it_is_called(
    tmp_path: Path,
) -> None:
    """The practice lab ships its nginx configuration as `ordered.conf` and
    `mismatched.conf`, one per scenario. Matching the literal name nginx.conf
    found none of them, and the timeout they exist to demonstrate is the
    defect a review is meant to catch."""
    path = tmp_path / "lb" / "profiles" / "ordered.conf"
    path.parent.mkdir(parents=True)
    path.write_text(
        "upstream api_backend {\n"
        "    server api:8000;\n"
        "    keepalive_timeout 60s;\n"
        "}\n"
        "server {\n"
        "    location / { proxy_pass http://api_backend; proxy_read_timeout 30s; }\n"
        "}\n"
    )

    found = read_artifacts(tmp_path).of(ArtifactKind.WEBSERVER)

    assert [a.path for a in found] == ["lb/profiles/ordered.conf"]
    assert found[0].facts["proxy_read_timeout"] == "30s"


def test_a_database_config_is_not_mistaken_for_a_web_server(tmp_path: Path) -> None:
    """A Postgres `primary.conf` has a `listen_addresses` and no `proxy_pass`.
    Sniffing for anything as generic as `listen` claims every .conf in the
    repository is nginx."""
    (tmp_path / "primary.conf").write_text(
        "listen_addresses = '*'\nmax_connections = 100\nwal_level = replica\n"
    )

    assert read_artifacts(tmp_path).of(ArtifactKind.WEBSERVER) == ()


def test_a_directive_that_appears_twice_reports_both_values(tmp_path: Path) -> None:
    """nginx scopes a directive to its block, and this reads no blocks. The
    upstream's keepalive and the server's are different numbers under one
    name, and reporting the first silently answers a question about the
    second."""
    (tmp_path / "nginx.conf").write_text(
        "upstream api { keepalive_timeout 60s; }\nserver { keepalive_timeout 75s; }\n"
    )

    facts = read_artifacts(tmp_path).of(ArtifactKind.WEBSERVER)[0].facts

    assert facts["keepalive_timeout"] == "60s, 75s"


def test_the_last_assignment_is_the_one_python_binds(tmp_path: Path) -> None:
    """A gunicorn config is executed, not parsed. A second `workers =` further
    down the file is the one that takes effect, and reporting the first
    reports a worker count the process never runs at."""
    (tmp_path / "gunicorn.conf.py").write_text(
        "workers = 2\nif os.environ.get('BIG'):\n    pass\nworkers = 4\n"
    )

    assert read_artifacts(tmp_path).of(ArtifactKind.WEBSERVER)[0].facts["workers"] == "4"


def test_gunicorn_reports_the_workers_a_pool_size_has_to_be_read_against(
    repo: Path,
) -> None:
    """A pool of 5 is not wrong. A pool of 5 per worker across 2 workers
    against a database that allows 10 connections is."""
    gunicorn = _one(repo, ArtifactKind.WEBSERVER, "gunicorn.conf.py")

    assert gunicorn.facts["workers"] == "2"
    assert gunicorn.facts["threads"] == "4"
    assert gunicorn.facts["timeout"] == "30"


# -- manifests and the lockfiles that should sit beside them ---------------


def test_a_manifest_with_no_lockfile_beside_it_is_named(repo: Path) -> None:
    """Unpinned transitive dependencies mean the build is not reproducible,
    and that the version reviewed is not the version deployed."""
    inventory = read_artifacts(repo)

    assert inventory.manifests_without_a_lockfile == ("frontend/package.json",)


def test_a_manifest_that_has_its_lockfile_is_not_named(repo: Path) -> None:
    pyproject = _one(repo, ArtifactKind.MANIFEST, "pyproject.toml")

    assert pyproject.facts["lockfile"] == "uv.lock"
    assert "lockfile" not in pyproject.absent


def test_the_lockfiles_themselves_are_inventoried(repo: Path) -> None:
    assert _paths(repo, ArtifactKind.LOCKFILE) == {"uv.lock"}


def test_a_lockfile_is_never_read_because_it_is_enormous_and_says_nothing(
    tmp_path: Path,
) -> None:
    """357KB of resolved hashes. Its presence is the fact; its content is not."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "uv.lock").write_text("version = 1\nsentinel-not-worth-reading\n")

    assert "sentinel-not-worth-reading" not in read_artifacts(tmp_path).model_dump_json()


# -- the rest --------------------------------------------------------------


def test_a_procfile_reports_what_the_platform_is_told_to_run(repo: Path) -> None:
    procfile = _one(repo, ArtifactKind.PROCFILE, "Procfile")

    assert "gunicorn app:app --workers 2" in procfile.facts["web"]
    assert "--concurrency=1" in procfile.facts["worker"]


def test_terraform_is_recorded_as_present(repo: Path) -> None:
    assert _paths(repo, ArtifactKind.TERRAFORM) == {"infra/main.tf"}


# -- cost, which is why this returns an inventory and not the files --------


def test_vendored_directories_are_not_walked(repo: Path) -> None:
    """A node_modules ships thousands of Dockerfiles nobody deploys."""
    assert _paths(repo, ArtifactKind.DOCKERFILE) == {"Dockerfile"}


def test_source_files_are_left_to_the_map(repo: Path) -> None:
    assert "backend/app.py" not in {a.path for a in read_artifacts(repo).artifacts}


def test_a_kind_is_capped_and_the_true_count_is_still_reported(tmp_path: Path) -> None:
    """A cap that silently drops files reports a smaller repository than the
    one under review. The count is what stops the cap from being a lie."""
    (tmp_path / "infra").mkdir()
    for index in range(30):
        (tmp_path / "infra" / f"m{index:02d}.tf").write_text("resource {}\n")

    inventory = read_artifacts(tmp_path)

    assert len(inventory.of(ArtifactKind.TERRAFORM)) < 30
    assert inventory.totals["terraform"] == 30


def test_a_repository_with_none_of_this_inventories_to_nothing(tmp_path: Path) -> None:
    """Most of a monorepo's directories ship no artefacts, and an empty
    inventory has to be an empty inventory rather than a crash."""
    (tmp_path / "app.py").write_text("x = 1\n")

    inventory = read_artifacts(tmp_path)

    assert inventory.artifacts == ()
    assert inventory.manifests_without_a_lockfile == ()
    assert inventory.tests_gate_the_merge is False
