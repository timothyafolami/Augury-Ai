"""Matching a finding to a defect we seeded.

This is the ground truth the whole evaluation rests on, so it is deliberately
strict in one direction and forgiving in the other: strict about which file,
because a real finding elsewhere is not this defect and counting it would make
recall reward volume; forgiving about where the identifying name appears,
because reviewers name a construct in the symbol field or in prose and
penalising that measures formatting rather than detection.
"""

from pathlib import Path

import pytest

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


# -- matching must not be a lottery ----------------------------------------
# An adversarial review scored recall 1.000 on B01 from five findings that
# described nothing seeded: "except" matched "an exception type is not
# declared", "balance" matched "should load-balance across replicas". Three of
# the five detections in the committed trajectory were earned that way.


def test_a_symbol_must_match_a_whole_word_not_a_fragment() -> None:
    """`except` inside `exception` is not a mention of the handler."""
    handler = defect(symbols=["except"], locations=["a.py"])

    assert not handler.found_in(
        report("a.py", "logger", "no structured logging; an exception here would be invisible")
    )


def test_the_whole_word_still_matches() -> None:
    handler = defect(symbols=["except"], locations=["a.py"])

    assert handler.found_in(report("a.py", "load", "the bare except swallows the failure"))


def test_a_hyphenated_neighbour_is_not_a_match() -> None:
    """`balance` inside `load-balance` is a different subject entirely."""
    wallet = defect(symbols=["balance"], locations=["a.py"])

    assert not wallet.found_in(
        report("a.py", "credit", "credit() should load-balance across read replicas")
    )


def test_a_symbol_with_an_underscore_matches_as_written() -> None:
    pool = defect(symbols=["pool_size"], locations=["a.py"])

    assert pool.found_in(report("a.py", "engine", "pool_size is 5 against 8 workers"))


def test_a_function_call_spelling_matches_the_bare_name() -> None:
    """Reviewers write `debit()` as often as `debit`, and penalising that
    measures formatting rather than detection."""
    lost_update = defect(symbols=["debit"], locations=["a.py"])

    assert lost_update.found_in(report("a.py", "wallet", "debit() reads then writes"))


def test_shipped_case_symbols_are_specific_enough_to_identify_a_defect() -> None:
    """A symbol that is a common English fragment turns recall into a lottery
    over whether a reviewer happened to use the word."""
    too_generic = {"except", "quote", "load", "charge", "balance", "list", "get", "set"}

    for case in load_cases():
        for seeded in case.defects:
            weak = {s for s in seeded.symbols if s.lower() in too_generic}
            assert not weak, (
                f"{case.id}/{seeded.id} identifies itself by {sorted(weak)}, which any "
                "finding in the right file could contain by accident"
            )


# -- inflection, but not derivation ----------------------------------------
# A whole-word matcher that rejects `leaks` scored a review saying "leaks the
# connection" as having found nothing, while a review whose mechanism was a
# single full stop scored 1.000 by putting the function name in the symbol
# field. Recall inverted: describing every defect correctly beat nothing, and
# saying nothing in the right files beat both.


@pytest.mark.parametrize(
    ("symbol", "prose"),
    [
        ("leak", "the session leaks a connection on the error path"),
        ("leak", "this is leaking one connection per failure"),
        ("leak", "a connection was leaked"),
        ("shed", "the queue never sheds"),
        ("retry", "it retries three times"),
        ("swallow", "the handler swallows the failure"),
    ],
)
def test_an_inflected_form_of_a_symbol_counts(symbol: str, prose: str) -> None:
    """Reviewers conjugate. Penalising that measures grammar, not detection."""
    assert defect(symbols=[symbol], locations=["a.py"]).found_in(report("a.py", "f", prose))


@pytest.mark.parametrize(
    ("symbol", "prose"),
    [
        ("except", "an exception type is not declared"),
        ("bound", "this is unbounded and grows forever"),
        ("count", "the accountant reconciles it"),
    ],
)
def test_a_different_word_sharing_a_prefix_does_not_count(symbol: str, prose: str) -> None:
    """`exception` is not a mention of `except`. That is the failure the
    whole-word rule was introduced for, and it must survive the fix."""
    assert not defect(symbols=[symbol], locations=["a.py"]).found_in(report("a.py", "f", prose))


def test_every_shipped_symbol_can_actually_match_something() -> None:
    """A symbol matching neither the code it points at nor its own defect
    description is inert: it cannot raise recall and it makes the answer key
    look more forgiving than it is."""
    from augury.evaluation.cases import _mentions

    for case in load_cases():
        for seeded in case.defects:
            source = " ".join(
                (case.repo / location).read_text(encoding="utf-8", errors="replace")
                for location in seeded.locations
                if (case.repo / location).is_file()
            )
            for symbol in seeded.symbols:
                assert _mentions(symbol, source) or _mentions(symbol, seeded.defect), (
                    f"{case.id}/{seeded.id}: {symbol!r} appears in neither the source "
                    "nor the description, so nothing can ever match it"
                )


def test_a_finding_that_says_nothing_has_not_found_anything() -> None:
    """Naming the right function with an empty mechanism scored a perfect
    recall. Detection requires a claim about what is wrong, not a pointer."""
    pointer = report("a.py", "debit", ".")

    assert not defect(symbols=["debit"], locations=["a.py"]).found_in(pointer)


def test_a_brief_but_real_mechanism_counts() -> None:
    """The bar is that something was said, not that it was said at length."""
    terse = report("a.py", "debit", "reads the balance then writes it back, unlocked")

    assert defect(symbols=["debit"], locations=["a.py"]).found_in(terse)
