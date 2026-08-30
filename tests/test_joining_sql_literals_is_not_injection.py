"""Splitting a long query across two string literals is formatting, not a bug.

`_weaves_a_query` flags a line that contains a SQL keyword and one of the
interpolation shapes. One of those shapes is a quote followed by `+`, which
is how a value is woven in -- and also how a long statement is wrapped onto
two lines, which is the ordinary way to write SQL in Go, Java and C++.

So `"SELECT * FROM t " + "WHERE id = ?"` was reported as injection, on a
query whose parameter is bound correctly. That costs a model call routing the
file to the security specialist, and risks the specialist agreeing with a
premise that was wrong.

The module already had a `_BOUND` pattern for placeholders, written with a
comment saying a file using one "is doing the correct thing". It was never
wired to anything. It is also not the right test on its own: a query can bind
one parameter and interpolate another, and that is a real defect.

The distinction that holds is what the `+` joins. Literal to literal is
formatting. Literal to expression is the bug.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages.source_signals import signals_in_source
from augury.core.cartography.model import Signal

SAFE = [
    ('String q = "SELECT * FROM t " + "WHERE id = ?";', "java", "literal join, bound"),
    ('q := "SELECT id, name " + "FROM users WHERE id = $1"', "go", "literal join, numbered"),
    (
        'const q = "SELECT * FROM orders " + "WHERE customer = $1 " + "ORDER BY id";',
        "typescript",
        "three literals",
    ),
    ('db.Query("SELECT * FROM t WHERE id = $1", id)', "go", "no join at all"),
]

WOVEN = [
    ('db.Query("SELECT * FROM t WHERE id = \'" + id + "\'")', "go", "value between literals"),
    (
        "pool.query(`SELECT * FROM orders WHERE id = $1 AND status = '${status}'`)",
        "typescript",
        "one bound and one interpolated",
    ),
    (
        'st.executeQuery("SELECT * FROM t WHERE name = \'" + name + "\'");',
        "java",
        "value between literals, java",
    ),
]


@pytest.mark.parametrize("source,language,why", SAFE, ids=[w for _, _, w in SAFE])
def test_a_query_split_across_literals_is_not_flagged(source: str, language: str, why: str) -> None:
    assert Signal.SECURITY not in signals_in_source(language, source), (
        f"{why}: the join is between two literals, so no value is woven in"
    )


@pytest.mark.parametrize("source,language,why", WOVEN, ids=[w for _, _, w in WOVEN])
def test_a_value_joined_into_a_query_is_still_flagged(source: str, language: str, why: str) -> None:
    assert Signal.SECURITY in signals_in_source(language, source), (
        f"{why}: this is the defect the detector exists for"
    )


def test_binding_one_parameter_does_not_excuse_interpolating_another() -> None:
    """Which is why the placeholder alone was never the right test.

    Suppressing on the presence of `$1` would have made this line clean, and
    it is a real injection with a correctly-bound parameter beside it.
    """
    mixed = "pool.query(`SELECT * FROM t WHERE a = $1 AND b = '${b}'`, [a])"

    assert Signal.SECURITY in signals_in_source("typescript", mixed)
