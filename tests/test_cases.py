"""Matching a finding to a defect we seeded.

This is the ground truth the whole evaluation rests on, so it is deliberately
strict in one direction and forgiving in the other: strict about which file,
because a real finding elsewhere is not this defect and counting it would make
recall reward volume; forgiving about where the identifying name appears,
because reviewers name a construct in the symbol field or in prose and
penalising that measures formatting rather than detection.
"""

from pathlib import Path

from augury.core.findings import Finding, Report, Severity
from augury.evaluation.cases import Defect, load_cases


def defect(**overrides: object) -> Defect:
    return Defect.model_validate(
        {
            "id": "D1",
            "lab_topic": "02-network/02",
            "defect": "the pool is smaller than the worker count",
            "locations": ["app/db.py"],
            "symbols": ["pool_size"],
            "verification": "load",
        }
        | overrides
    )


def report(path: str, symbol: str, mechanism: str = "the pool is small") -> Report:
    return Report(
        findings=(
            Finding(
                path=path,
                line=10,
                layer="network",
                symbol=symbol,
                mechanism=mechanism,
                severity=Severity.HIGH,
                remediation="raise it",
            ),
        )
    )


def test_a_finding_at_the_seeded_location_counts() -> None:
    assert defect().found_in(report("app/db.py", "pool_size"))


def test_a_finding_in_another_file_does_not_count() -> None:
    assert not defect().found_in(report("app/main.py", "read_order"))


def test_the_right_file_but_an_unrelated_symbol_does_not_count() -> None:
    assert not defect().found_in(report("app/db.py", "DATABASE_URL"))


def test_the_name_may_appear_in_the_prose_instead_of_the_symbol_field() -> None:
    assert defect().found_in(report("app/db.py", "engine", "pool_size is 5 against 8 workers"))


def test_an_empty_report_finds_nothing() -> None:
    assert not defect().found_in(Report())


def test_matching_ignores_case() -> None:
    assert defect(symbols=["Pool_Size"]).found_in(report("app/db.py", "pool_size"))


def test_every_shipped_case_has_a_repository_on_disk() -> None:
    cases = load_cases()

    assert cases, "no evaluation cases found"
    for case in cases:
        assert case.repo.is_dir(), f"{case.id} has no repository"
        assert any(case.repo.rglob("*")), f"{case.id} repository is empty"


def test_shipped_case_locations_point_at_files_that_exist() -> None:
    """A location typo makes a defect permanently undetectable and silently
    caps recall at less than one."""
    for case in load_cases():
        for seeded in case.defects:
            for location in seeded.locations:
                assert (case.repo / location).is_file(), (
                    f"{case.id}/{seeded.id} names {location}, which is not in the repository"
                )


def test_a_shipped_case_repository_is_a_real_path(tmp_path: Path) -> None:
    for case in load_cases():
        assert case.repo.name == "repo"
