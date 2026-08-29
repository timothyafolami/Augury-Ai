"""A document about a service, not a list of lines.

On a repository of a few hundred modules a findings table is the wrong
artefact: nobody triages 139 rows. What a team can act on is a document that
says what the service is, what its deployment declares, what its schema and
dependencies say, which defects were found and where, and -- the part most
reports omit -- how much was not looked at.

Everything the report states about coverage is arithmetic. A report that
implies it read a repository it sampled is worse than no report.
"""

from __future__ import annotations

from augury.core.findings import Finding, Report, Severity
from augury.core.report import write_report
from augury.core.scheduling import Coverage
from augury.core.schema.model import SchemaFinding
from augury.core.survey.model import BackingService, Service, Survey


def _survey() -> Survey:
    return Survey(
        services=(
            Service(name="api", source_root="backend", ports=("8000:8000",)),
            Service(
                name="worker",
                source_root="backend",
                command="celery -A src.tasks.app worker --concurrency=1",
            ),
        ),
        backing=(BackingService(name="redis", image="redis:7", kind="cache or queue"),),
        source_roots=("backend",),
    )


def _report() -> Report:
    return Report(
        findings=(
            Finding(
                path="backend/app/api/deps.py",
                line=201,
                layer="network",
                symbol="get_current_user",
                mechanism="A blocking Stripe call sits inside an async dependency.",
                severity=Severity.HIGH,
                remediation="Move it behind a thread, or cache the result.",
            ),
        ),
        coverage=Coverage(analysed=["backend/app/api/deps.py"], stopped_because="budget exhausted"),
        usd=0.45,
        seconds=537.0,
    )


SCHEMA = (
    SchemaFinding(
        rule="index-blocks-writes",
        path="alembic/versions/0001.py",
        line=41,
        detail="builds an index on `users` without CONCURRENTLY",
        remediation="postgresql_concurrently=True",
    ),
)


def _write(**kwargs: object) -> str:
    defaults = {
        "name": "interview-api",
        "survey": _survey(),
        "report": _report(),
        "schema": SCHEMA,
        "dependencies": (),
        "modules": 261,
        "unreachable": 88,
    }
    return write_report(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_the_report_says_what_the_service_is() -> None:
    text = _write()

    assert "interview-api" in text
    assert "api" in text and "worker" in text
    assert "redis" in text


def test_the_report_quotes_the_concurrency_the_deployment_declares() -> None:
    """A capacity ceiling that exists in no source file."""
    assert "--concurrency=1" in _write()


def test_the_report_states_coverage_as_a_fraction_not_as_a_claim() -> None:
    text = _write()

    assert "1 of 261" in text
    assert "budget exhausted" in text


def test_the_report_says_how_much_no_request_reaches() -> None:
    assert "88" in _write()


def test_schema_and_code_findings_are_separate_sections() -> None:
    text = _write()

    assert "## Schema" in text
    assert "## Code" in text
    assert "index-blocks-writes" in text
    assert "get_current_user" in text


def test_a_section_with_nothing_in_it_says_so() -> None:
    """An empty heading reads as a bug. A sentence reads as a result."""
    text = _write(schema=(), dependencies=())

    assert "No schema findings" in text


def test_the_report_never_claims_a_coverage_it_did_not_have() -> None:
    """The sentence a reader will quote back, so it has to be exact."""
    text = _write()

    assert "read 1 of 261" in text
    assert "reviewed the repository" not in text.lower()
