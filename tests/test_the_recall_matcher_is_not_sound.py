"""What the seeded-recall matcher will and will not credit.

Recall is the one metric here scored by matching model-authored prose against a
manifest, and prose matching cannot distinguish a correct diagnosis from a
wrong one that happens to mention the right word. These tests do not assert
that the matcher is right. They pin exactly how it is wrong, so the number is
published with its error bars visible rather than with a claim of soundness.

Every case below was produced by running the shipped matcher, not imagined.
"""

from __future__ import annotations

from augury.core.findings import Finding, Report, Severity
from augury.evaluation.cases import load_cases


def _case(identifier: str) -> object:
    return next(c for c in load_cases() if c.id == identifier)


def _finding(path: str, symbol: str, mechanism: str) -> Finding:
    return Finding(
        path=path,
        line=1,
        layer="data",
        symbol=symbol,
        mechanism=mechanism,
        severity=Severity.HIGH,
        remediation="r",
    )


def _report(*findings: Finding) -> Report:
    return Report(findings=findings)


def test_a_review_asserting_the_code_is_correct_scores_a_perfect_recall() -> None:
    """The matcher counts words and tokens, never the polarity of the claim.

    Five sentences, each asserting the opposite of the seeded defect, credited
    with finding all five. This is the ceiling on how much any recall number in
    this project can be trusted.
    """
    b01 = _case("B01")
    report = _report(
        _finding("app/services/wallet.py", "debit", "The debit path is atomic and correct."),
        _finding(
            "app/api/orders.py", "list_orders", "The list_orders endpoint is efficient and fine."
        ),
        _finding(
            "app/clients/payments.py", "charge", "The retry budget here is generous and safe."
        ),
        _finding(
            "app/repositories/orders.py",
            "list_for_customer",
            "Returns an empty list, which is correct.",
        ),
        _finding(
            "app/clients/shipping.py", "quote", "The timeout configuration is already correct here."
        ),
    )
    assert len(b01.found_by(report)) == 5  # type: ignore[attr-defined]


def test_a_correct_diagnosis_in_other_words_scores_nothing() -> None:
    """The inverse failure, which is the expensive one.

    A finding that names the right file and the right mechanism, using none of
    the manifest's four chosen tokens, is a miss.
    """
    c01 = _case("C01")
    report = _report(
        _finding(
            "app/store/session.py",
            "get_session",
            "The connection is never returned to the pool when the body raises, "
            "so the pool drains under errors.",
        )
    )
    assert c01.found_by(report) == ()  # type: ignore[attr-defined]


def test_a_wrong_diagnosis_that_names_the_right_function_is_credited() -> None:
    """The false positive in the published run, reproduced exactly.

    C01-3 is a session leaked on the exception path. This finding diagnoses
    pool sizing, and its remediation would not fix the leak. It is credited
    because the prose contains `with_session`.
    """
    c01 = _case("C01")
    report = _report(
        _finding(
            "app/store/session.py",
            "engine",
            "SQLAlchemy engine is configured with pool_size=10 and max_overflow=0, so only "
            "ten DB connections are available; 40 concurrent with_session calls will exceed "
            "this, causing connection blocking and worker saturation.",
        )
    )
    assert "C01-3" in c01.found_by(report)  # type: ignore[attr-defined]


def test_a_hyphenated_compound_is_not_matched() -> None:
    """`read-timeout` does not match `timeout`: the boundary excludes hyphen."""
    b01 = _case("B01")
    report = _report(
        _finding(
            "app/clients/shipping.py",
            "quote",
            "No read-timeout is configured on the HTTP client, so one slow upstream "
            "pins every worker.",
        )
    )
    assert b01.found_by(report) == ()  # type: ignore[attr-defined]


def test_a_path_with_a_leading_dot_slash_matches_nothing() -> None:
    b01 = _case("B01")
    report = _report(
        _finding(
            "./app/clients/shipping.py",
            "quote",
            "The AsyncClient is built with timeout=None, so a slow upstream pins a worker.",
        )
    )
    assert b01.found_by(report) == ()  # type: ignore[attr-defined]
