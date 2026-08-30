"""The one property this project cannot get wrong.

Augury is pointed at other people's repositories, and a working service keeps
a live credential in a file beside its source. Reading that file would put it
in a prompt, a trajectory that is committed and handed to a judge, and a report
somebody pastes into an issue.

Every part of this is refused separately elsewhere. This asserts the whole
path at once, because the parts have been correct individually before while the
route between them was open, and because a property that is only true in
pieces is a property nobody can rely on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Shaped exactly like the real thing and belonging to nobody, so a scanner
# finding this file finds a test rather than an incident.
FAKE_KEY = "gsk_" + "0" * 48
FAKE_AWS = "AKIA" + "Q" * 16


@pytest.fixture
def a_service_with_a_live_env(tmp_path: Path) -> Path:
    repo = tmp_path / "service"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text(
        "import os\n\n\ndef handler():\n    return os.environ['GROQ_API_KEY']\n",
        encoding="utf-8",
    )
    (repo / "docker-compose.yml").write_text(
        "services:\n  api:\n    build: .\n    ports: ['8000:8000']\n", encoding="utf-8"
    )
    (repo / ".env").write_text(
        f"GROQ_API_KEY={FAKE_KEY}\nAWS_ACCESS_KEY_ID={FAKE_AWS}\n", encoding="utf-8"
    )
    # Committed, holds no secret, and genuinely useful to a reviewer.
    (repo / ".env.example").write_text("GROQ_API_KEY=\n", encoding="utf-8")
    return repo


def test_the_map_never_holds_it(a_service_with_a_live_env: Path) -> None:
    from augury.core.cartography.mapper import Cartographer

    repo = Cartographer(a_service_with_a_live_env).map()

    assert not [m for m in repo.modules if Path(m.path).name == ".env"]


def test_the_artifact_inventory_never_holds_it(a_service_with_a_live_env: Path) -> None:
    """A second refusal, independent of the first. Either alone would do, and
    two mean a change to one of them cannot open the route by itself."""
    from augury.core.artifacts import read_artifacts

    inventory = read_artifacts(a_service_with_a_live_env)

    assert not [a for a in inventory.artifacts if Path(a.path).name == ".env"]


def test_the_example_beside_it_is_still_read(a_service_with_a_live_env: Path) -> None:
    """Refusing everything shaped like an env file would cost the reviewer the
    one that is committed on purpose and says what the service needs."""
    from augury.core.artifacts import holds_live_credentials

    assert holds_live_credentials(".env")
    assert not holds_live_credentials(".env.example")


def test_the_deployment_pass_never_opens_it(a_service_with_a_live_env: Path) -> None:
    from augury.core.artifacts import read_artifacts
    from augury.core.artifacts.checks import deployment_findings

    inventory = read_artifacts(a_service_with_a_live_env)
    findings = deployment_findings(inventory.artifacts, root=a_service_with_a_live_env)

    assert FAKE_KEY not in " ".join(f"{f.detail} {f.remediation} {f.path}" for f in findings)


def test_nothing_the_review_would_publish_carries_it(a_service_with_a_live_env: Path) -> None:
    """The end of the path: everything a run writes down, searched for the key."""
    from augury.core.artifacts import read_artifacts
    from augury.core.artifacts.checks import deployment_findings
    from augury.core.cartography.mapper import Cartographer
    from augury.core.findings import Report
    from augury.core.report import write_report
    from augury.core.survey import Surveyor

    root = a_service_with_a_live_env
    found = Surveyor(root).survey()
    repo = Cartographer(root).map()
    deployment = deployment_findings(read_artifacts(root).artifacts, root=root)

    written = write_report(
        name=root.name,
        survey=found,
        report=Report(findings=(), model_id="m", usd=0.0, seconds=1.0),
        schema=(),
        dependencies=(),
        deployment=deployment,
        modules=len(repo.modules),
        unreachable=len(repo.unreachable),
        reading={},
    )

    assert FAKE_KEY not in written
    assert FAKE_AWS not in written


def test_a_secret_that_reached_a_trajectory_anyway_is_redacted() -> None:
    """The last line of defence, for a secret that arrives inside source rather
    than from a file this refuses to open. A trajectory is committed."""
    from augury.core.trajectory import redact

    assert FAKE_KEY not in redact(f"the client used {FAKE_KEY} to authenticate")
    assert FAKE_AWS not in redact(f"aws_access_key_id = {FAKE_AWS}")
