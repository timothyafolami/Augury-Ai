"""The document is the artefact `report` produces. It must not deny its own work.

After `--prove`, `_settle` attaches a Measurement to each proven finding and
the document rendered none of it: a claim measured at 41ms against a predicted
250-900ms band printed as an open claim, and the document closed with "Nothing
here was executed."

False, and false in the direction that hides a refutation.
"""

from __future__ import annotations

from augury.core.findings import Finding, Measurement, Report, Severity
from augury.core.report import write_report
from augury.core.schema.model import SchemaFinding
from augury.core.schemas import Comparator, Outcome, Prediction
from augury.core.survey.model import Survey


def _band() -> Prediction:
    return Prediction(
        metric="http_req_duration_p99",
        comparator=Comparator.BETWEEN,
        value=250.0,
        upper=900.0,
        unit="ms",
        condition="200 rps for 60s",
    )


def _finding(measurement: Measurement | None = None) -> Finding:
    return Finding(
        path="app/api.py",
        line=10,
        layer="network",
        symbol="list_orders",
        mechanism="The handler issues one query per row.",
        remediation="Use a join.",
        severity=Severity.HIGH,
        prediction=_band(),
        measurement=measurement,
    )


def _document(*findings: Finding) -> str:
    return write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=_report(*findings),
        schema=(),
        dependencies=(),
        modules=10,
        unreachable=0,
        reading={},
    )


def _report(*findings: Finding) -> Report:
    return Report(findings=tuple(findings), model_id="m", usd=0.0, seconds=1.0)


def test_a_measured_finding_shows_what_was_measured() -> None:
    said = _document(_finding(Measurement(value=41.0, experiment="e.py", detail="ran")))

    assert "41" in said


def test_a_measured_finding_shows_the_verdict() -> None:
    """A miss is the most valuable line in the document and it was invisible."""
    said = _document(_finding(Measurement(value=41.0, experiment="e.py", detail="ran")))

    assert Outcome.MISS.value in said.lower()


def test_a_document_with_a_measurement_does_not_claim_nothing_was_executed() -> None:
    said = _document(_finding(Measurement(value=41.0, experiment="e.py", detail="ran")))

    assert "Nothing here was executed" not in said


def test_a_document_without_measurements_still_says_nothing_was_executed() -> None:
    said = _document(_finding())

    assert "Nothing here was executed" in said


def test_a_band_prints_both_of_its_bounds() -> None:
    """`p.value:g` alone printed "between 250ms", which is not a band.

    As published the claim could not be checked against anything, which is the
    one property every claim here is supposed to have.
    """
    said = _document(_finding())

    assert "900" in said


def test_withdrawn_claims_appear_where_the_document_says_they_are_recorded() -> None:
    """It asserted the reasons are recorded and showed none of them."""
    from augury.core.findings import Dropped

    document = write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=Report(
            findings=(_finding(),),
            dropped=(Dropped(symbol="q", path="a.py", reason="the migrations index it"),),
            model_id="m",
            usd=0.0,
            seconds=1.0,
        ),
        schema=(),
        dependencies=(),
        modules=10,
        unreachable=0,
        reading={},
    )

    assert "the migrations index it" in document


def test_partial_coverage_is_not_rounded_up_to_all_of_it() -> None:
    """249 of 250 rendered as (100%)."""
    from augury.core.scheduling.scheduler import Coverage

    document = write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=Report(
            findings=(_finding(),),
            coverage=Coverage(analysed=[f"m{n}.py" for n in range(249)]),
            model_id="m",
            usd=0.0,
            seconds=1.0,
        ),
        schema=(),
        dependencies=(),
        modules=250,
        unreachable=0,
        reading={},
    )

    assert "(100%)" not in document


def _deployment() -> tuple[SchemaFinding, ...]:
    return (
        SchemaFinding(
            rule="container-runs-as-root",
            path="backend/Dockerfile",
            line=1,
            detail="the final stage declares no USER, so every process runs as uid 0",
            remediation="Add a USER instruction to the final stage",
        ),
    )


def test_the_document_carries_the_deployment_findings() -> None:
    """On a real backend these outnumber the code findings ten to one, and the
    document a team acts on had none of them."""
    said = write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=_report(_finding()),
        schema=(),
        dependencies=(),
        deployment=_deployment(),
        modules=10,
        unreachable=0,
        reading={},
    )

    assert "container-runs-as-root" in said


def test_the_document_carries_the_synthesis() -> None:
    """The most senior thing in the review, and it was only in the browser."""
    from augury.agents.synthesis import Citation, Observation

    said = write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=_report(_finding()),
        schema=(),
        dependencies=(),
        synthesis=(
            Observation(
                mechanism="Two unsynchronised singletons share one loader",
                consequence="Two concurrent first requests each load the model",
                citations=(
                    Citation(path="a.py", line=1, symbol="load", layer="concurrency"),
                    Citation(path="b.py", line=2, symbol="warm", layer="craft"),
                ),
            ),
        ),
        modules=10,
        unreachable=0,
        reading={},
    )

    assert "unsynchronised singletons" in said
    assert "concurrency" in said


def test_a_document_with_no_deployment_findings_says_nothing_about_them() -> None:
    """A heading over an empty section reads as a section that found nothing,
    which is not the same as a section that did not run."""
    said = write_report(
        name="svc",
        survey=Survey(services=(), source_roots=()),
        report=_report(_finding()),
        schema=(),
        dependencies=(),
        modules=10,
        unreachable=0,
        reading={},
    )

    assert "Deployment" not in said


def test_both_clients_hand_the_document_what_it_can_now_carry() -> None:
    """A parameter with a default is a parameter a caller can forget.

    The document gained deployment findings and a synthesis, and both are
    optional so nothing broke when they were added. That is exactly how a
    section stays permanently empty: the renderer supports it, the callers do
    not pass it, and no test fails.
    """
    import ast
    from pathlib import Path

    for source in ("src/augury/cli/main.py", "src/augury/server/app.py"):
        text = Path(source).read_text(encoding="utf-8")
        tree = ast.parse(text)
        handed: set[str] = set()
        wanted = {"write_report", "as_document"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            # The renderer is handed to a thread rather than called, so it is
            # an argument there and the callee here. Both are the same call.
            offloaded = any(getattr(arg, "id", None) in wanted for arg in node.args)
            if called not in wanted and not offloaded:
                continue
            handed |= {kw.arg for kw in node.keywords if kw.arg}
        assert "deployment" in handed, f"{source} never passes the deployment findings"
