"""Recording what the agents actually did.

The submission has to show "what the agent did and how its tools responded,
the feedback that shaped its next step, plus any retries or human checkpoints".
That is a feature, not a document: it has to be produced by a run rather than
written about one afterwards.

It is also the artefact that makes a published number checkable. A reader who
doubts a finding can read the prompt that produced it.
"""

import json
from pathlib import Path

import pytest

from augury.agents.augury import AuguryReviewer
from augury.core.adapters.base import Usage
from augury.core.cartography import Cartographer
from augury.core.trajectory import Trajectory, redact
from tests.test_augury_arm import make_repo, model


def test_records_each_step_in_order(tmp_path: Path) -> None:
    trace = Trajectory(tmp_path / "run.jsonl")

    trace.record(agent="cartographer", action="mapped", detail={"modules": 17})
    trace.record(agent="scheduler", action="selected", detail={"path": "app/db.py"})

    steps = _read(tmp_path / "run.jsonl")
    assert [s["agent"] for s in steps] == ["cartographer", "scheduler"]


def test_a_model_call_records_the_prompt_and_what_came_back(tmp_path: Path) -> None:
    """A reader who doubts a finding should be able to read the prompt that
    produced it, rather than being asked to trust the summary."""
    trace = Trajectory(tmp_path / "run.jsonl")

    trace.record_call(
        agent="analyst:data",
        prompt="review app/db.py",
        response={"findings": []},
        usage=Usage(input_tokens=100, output_tokens=50, usd=0.001),
        retries=0,
    )

    step = _read(tmp_path / "run.jsonl")[0]
    assert step["prompt"] == "review app/db.py"
    assert step["response"] == {"findings": []}
    assert step["usage"]["usd"] == 0.001


def test_retries_are_recorded_rather_than_smoothed_over(tmp_path: Path) -> None:
    """A run that needed three attempts is a different run from one that
    needed none, and hiding it would overstate how well this works."""
    trace = Trajectory(tmp_path / "run.jsonl")

    trace.record_call(agent="analyst:data", prompt="p", response={}, usage=Usage(), retries=2)

    assert _read(tmp_path / "run.jsonl")[0]["retries"] == 2


def test_deterministic_steps_are_recorded_too(tmp_path: Path) -> None:
    """Two of the agents never call a model. A trajectory that only shows the
    model calls would misrepresent where the work happens."""
    trace = Trajectory(tmp_path / "run.jsonl")

    trace.record(agent="scheduler", action="selected", detail={"value": 3.2})

    step = _read(tmp_path / "run.jsonl")[0]
    assert step["model_call"] is False


def test_an_api_key_never_reaches_the_trace(tmp_path: Path) -> None:
    """Trajectories are committed and handed to judges. A prompt containing a
    reviewed repository's secret must not be published with it."""
    trace = Trajectory(tmp_path / "run.jsonl")

    trace.record_call(
        agent="analyst:security",
        prompt="found GROQ_API_KEY=gsk_live_abcdefghijklmnopqrstuvwxyz012345 in config",
        response={},
        usage=Usage(),
        retries=0,
    )

    written = (tmp_path / "run.jsonl").read_text()
    assert "gsk_live_abcdefghijklmnopqrstuvwxyz012345" not in written
    assert "REDACTED" in written


def test_the_file_is_created_even_when_nothing_happened(tmp_path: Path) -> None:
    """An empty trajectory is evidence too: it says the run did nothing."""
    Trajectory(tmp_path / "nested" / "run.jsonl")

    assert (tmp_path / "nested" / "run.jsonl").is_file()


def test_every_line_is_valid_json_on_its_own(tmp_path: Path) -> None:
    """So a reader can grep it, and a partial file from an interrupted run is
    still readable up to the point it stopped."""
    trace = Trajectory(tmp_path / "run.jsonl")
    for index in range(3):
        trace.record(agent="scheduler", action="selected", detail={"n": index})

    for line in (tmp_path / "run.jsonl").read_text().splitlines():
        json.loads(line)


def _read(path: Path) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "secret",
    [
        "gsk_live_abcdefghijklmnopqrstuvwxyz012345",
        "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
    ],
)
def test_every_credential_shape_is_redacted(secret: str) -> None:
    """The first version of this matched only up to the first underscore, fell
    short of its own length floor, and published the key."""
    assert secret not in redact(f"found {secret} in app/config.py")


def test_ordinary_text_is_left_alone() -> None:
    """A redactor that mangles the prompt makes the trajectory unreadable,
    which defeats the point of publishing it."""
    prose = "pool_size is 5 against 8 workers, so p99 exceeds 1000ms at 250rps"

    assert redact(prose) == prose


# -- recording an actual review --------------------------------------------


async def test_a_review_records_what_each_agent_did(tmp_path: Path) -> None:
    """The trajectory has to be produced by a run. Written afterwards it would
    be a summary, and a summary is exactly what a reader cannot check."""
    root = make_repo(tmp_path / "repo")
    trace = Trajectory(tmp_path / "run.jsonl")

    await AuguryReviewer(model(), trajectory=trace).review(Cartographer(root).map(), root)

    steps = [json.loads(line) for line in (tmp_path / "run.jsonl").read_text().splitlines()]
    agents = {step["agent"] for step in steps}

    assert "cartographer" in agents, "the map is where a review starts"
    assert "scheduler" in agents, "what was read, and why it was chosen"
    assert any(a.startswith("triage") for a in agents)
    assert any(a.startswith("analyst:") for a in agents)


async def test_the_deterministic_agents_appear_without_a_model_call(tmp_path: Path) -> None:
    """Two of the agents never consult a model. A trace showing only model
    calls would put the work in the wrong place."""
    root = make_repo(tmp_path / "repo")
    trace = Trajectory(tmp_path / "run.jsonl")

    await AuguryReviewer(model(), trajectory=trace).review(Cartographer(root).map(), root)

    steps = [json.loads(line) for line in (tmp_path / "run.jsonl").read_text().splitlines()]
    deterministic = [s for s in steps if s["agent"] in {"cartographer", "scheduler"}]

    assert deterministic
    assert all(step["model_call"] is False for step in deterministic)


async def test_a_review_without_a_trajectory_still_works(tmp_path: Path) -> None:
    """Recording is optional. A run that did not ask for it must not fail."""
    root = make_repo(tmp_path / "repo")

    report = await AuguryReviewer(model()).review(Cartographer(root).map(), root)

    assert report is not None


# -- redaction must fail closed --------------------------------------------
# An adversarial review found the private-key rule matched only the BEGIN
# header, so re.sub replaced that one line and published the key body with the
# marker that secret scanners key on removed. Strictly worse than not matching:
# the leak became complete and undetectable by tooling.
#
# These assert on the ABSENCE OF THE SECRET, never on the presence of the word
# REDACTED, because the PEM case passed the latter check while leaking.


PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAvR8xN2kQwJ4dLm3pYzT1sB7cF9gH0jK2lM4nO6pQ8rS1tU3vW
5xY7zA9bC1dE3fG5hI7jK9lM1nO3pQ5rS7tU9vW1xY3zA5bC7dE9fG1hI3jK5lM7n
-----END RSA PRIVATE KEY-----"""


def test_a_private_key_body_is_removed_not_just_its_header() -> None:
    redacted = redact(f"found in deploy/key.pem:\n{PRIVATE_KEY}\n")

    assert "MIIEowIBAAKCAQEAvR8xN2kQwJ4dLm3pYzT1sB7cF9gH0jK2lM4nO6pQ8rS1tU3vW" not in redacted
    assert "5xY7zA9bC1dE3fG5hI7jK9lM1nO3pQ5rS7tU9vW1xY3zA5bC7dE9fG1hI3jK5lM7n" not in redacted


@pytest.mark.parametrize(
    ("secret", "what"),
    [
        ("postgres://admin:S3cr3tP4ssw0rd@db.internal:5432/orders", "database URI password"),
        ("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "AWS secret access key"),
        ("github_pat_11ABCDEFG0abcdefghijklABCDEFGHIJKLMNOPQRSTUVWXYZ0123", "fine-grained PAT"),
        ("xoxb-123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx", "Slack bot token"),
        ("AIzaSyD-1234567890abcdefghijklmnopqrstuvw", "Google API key"),
        ("gho_16C7e42F292c6912E7710c838347Ae178B4a12", "GitHub OAuth token"),
        ("PASSWORD=hunter2correcthorsebatterystaple", "a password assignment"),
    ],
)
def test_the_shapes_a_reviewed_repository_actually_contains(secret: str, what: str) -> None:
    """Case B01 is itself a Postgres service, so a connection string in a
    reviewed file is the expected case rather than a hypothetical."""
    body = secret.split("://")[-1].split("=")[-1]

    assert body not in redact(f"in app/config.py: {secret}"), f"leaked a {what}"
