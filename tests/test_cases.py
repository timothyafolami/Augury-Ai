"""A case is a repository plus the defect we put in it.

Because we seeded the defect, "did the reviewer find it" has an objective
answer. That makes Seeded Defect Recall the strongest number available: unlike
every other metric here, it cannot be gamed by saying less, because saying less
can only lower it.
"""

import json
from pathlib import Path

import pytest

from augury.core.findings import Finding, Report, Severity
from augury.evaluation.cases import Case, load_cases


def a_finding(path: str, symbol: str) -> Finding:
    return Finding(
        path=path,
        line=10,
        layer="network",
        symbol=symbol,
        mechanism="the pool is smaller than the worker count",
        severity=Severity.HIGH,
        remediation="raise it",
    )


def test_every_shipped_case_loads() -> None:
    cases = load_cases()

    assert cases, "no evaluation cases found"
    for case in cases:
        assert case.repo.is_dir(), f"{case.id} has no repository"
        assert case.defect, f"{case.id} does not say what was seeded"
        assert case.lab_topic, f"{case.id} does not cite the lab topic it comes from"


def test_a_finding_at_the_seeded_location_counts_as_detection(tmp_path: Path) -> None:
    case = _case(tmp_path, locations=["app/db.py"], symbols=["pool_size"])

    assert case.detected_by(Report(findings=(a_finding("app/db.py", "pool_size"),)))


def test_a_finding_elsewhere_does_not_count(tmp_path: Path) -> None:
    """Finding something real in another file is not finding this defect.
    Counting it would make recall reward volume."""
    case = _case(tmp_path, locations=["app/db.py"], symbols=["pool_size"])

    assert not case.detected_by(Report(findings=(a_finding("app/main.py", "read_order"),)))


def test_the_right_file_but_an_unrelated_symbol_does_not_count(tmp_path: Path) -> None:
    case = _case(tmp_path, locations=["app/db.py"], symbols=["pool_size"])

    assert not case.detected_by(Report(findings=(a_finding("app/db.py", "DATABASE_URL"),)))


def test_the_symbol_may_appear_in_the_mechanism_rather_than_the_symbol_field(
    tmp_path: Path,
) -> None:
    """Reviewers name the construct in prose as often as in the symbol field,
    and penalising that would measure formatting rather than detection."""
    case = _case(tmp_path, locations=["app/db.py"], symbols=["pool_size"])
    finding = a_finding("app/db.py", "engine").model_copy(
        update={"mechanism": "pool_size is 5 against 8 workers"}
    )

    assert case.detected_by(Report(findings=(finding,)))


def test_an_empty_report_detects_nothing(tmp_path: Path) -> None:
    assert not _case(tmp_path, locations=["app/db.py"], symbols=["x"]).detected_by(Report())


def _case(tmp_path: Path, **overrides: object) -> Case:
    payload = {
        "id": "T01",
        "name": "test-case",
        "lab_topic": "02-network/02",
        "defect": "a seeded defect",
        "locations": ["app/db.py"],
        "symbols": ["pool_size"],
        "verification": "load",
        "expected_metric": "http_req_duration_p99",
    } | overrides
    directory = tmp_path / "T01"
    (directory / "repo").mkdir(parents=True)
    (directory / "case.json").write_text(json.dumps(payload))
    return load_cases(tmp_path)[0]


@pytest.mark.parametrize("field", ["defect", "lab_topic", "symbols"])
def test_a_case_missing_its_ground_truth_is_refused(tmp_path: Path, field: str) -> None:
    """A case that does not say what was seeded cannot measure recall."""
    payload: dict[str, object] = {
        "id": "T02",
        "name": "broken",
        "lab_topic": "x",
        "defect": "y",
        "locations": ["a.py"],
        "symbols": ["s"],
        "verification": "load",
        "expected_metric": "m",
    }
    payload[field] = [] if field == "symbols" else ""
    directory = tmp_path / "T02"
    (directory / "repo").mkdir(parents=True)
    (directory / "case.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError):
        load_cases(tmp_path)
