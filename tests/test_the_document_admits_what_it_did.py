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
