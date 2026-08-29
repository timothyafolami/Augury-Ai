"""A realistic repository has more than one thing wrong with it.

One defect per case cannot express the thing the pipeline claims to be better
at: holding recall while the amount of code grows. With several defects in one
repository, recall becomes a fraction rather than a coin flip, and a reviewer
that finds two of five is distinguishable from one that finds four.
"""

import json
from pathlib import Path

import pytest

from augury.core.findings import Finding, Report, Severity
from augury.evaluation.cases import Case, load_cases


def finding(path: str, symbol: str, mechanism: str = "") -> Finding:
    return Finding(
        path=path,
        line=10,
        layer="data",
        symbol=symbol,
        mechanism=mechanism or "something is wrong",
        severity=Severity.HIGH,
        remediation="fix it",
    )


def case_with(tmp_path: Path, defects: list[dict[str, object]]) -> Case:
    payload = {
        "id": "T01",
        "name": "multi",
        "repo_description": "a service",
        "defects": defects,
    }
    directory = tmp_path / "T01"
    (directory / "repo").mkdir(parents=True)
    (directory / "case.json").write_text(json.dumps(payload))
    return load_cases(tmp_path)[0]


def a_defect(**overrides: object) -> dict[str, object]:
    return {
        "id": "D1",
        "lab_topic": "03-data/01",
        "defect": "lost update under READ COMMITTED",
        "locations": ["app/wallet.py"],
        "symbols": ["debit"],
        "verification": "differential",
    } | overrides


def test_recall_is_the_share_of_seeded_defects_found(tmp_path: Path) -> None:
    case = case_with(
        tmp_path,
        [
            a_defect(id="D1", locations=["a.py"], symbols=["debit"]),
            a_defect(id="D2", locations=["b.py"], symbols=["serialize"]),
            a_defect(id="D3", locations=["c.py"], symbols=["charge"]),
        ],
    )

    report = Report(findings=(finding("a.py", "debit"), finding("c.py", "charge")))

    assert case.recall(report) == pytest.approx(2 / 3)
    assert case.found_by(report) == ("D1", "D3")


def test_finding_the_same_defect_twice_counts_once(tmp_path: Path) -> None:
    """Otherwise recall rewards a reviewer that repeats itself."""
    case = case_with(tmp_path, [a_defect(id="D1", locations=["a.py"], symbols=["debit"])])

    report = Report(findings=(finding("a.py", "debit"), finding("a.py", "debit")))

    assert case.recall(report) == 1.0


def test_a_case_with_no_defects_is_refused(tmp_path: Path) -> None:
    """A case that seeds nothing cannot measure recall, and a control repo is
    a different thing with a different name."""
    with pytest.raises(ValueError):
        case_with(tmp_path, [])


def test_a_report_finding_nothing_scores_zero_not_undefined(tmp_path: Path) -> None:
    case = case_with(tmp_path, [a_defect()])

    assert case.recall(Report()) == 0.0


def test_every_shipped_case_declares_its_defects_and_their_lab_topics() -> None:
    for case in load_cases():
        assert case.defects, f"{case.id} seeds nothing"
        for defect in case.defects:
            assert defect.lab_topic, f"{case.id}/{defect.id} cites no lab topic"
            assert defect.symbols, f"{case.id}/{defect.id} cannot be detected"
