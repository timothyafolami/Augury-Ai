"""Collapsing repeats must not merge two bugs that merely start alike.

`_shape` kept the first eight non-specific words, and the ninth word is where
the mechanism usually lives. Four handlers that "do not validate the request
body before ..." doing four different things with it became one finding: three
HIGH severities replaced by the survivor's MEDIUM, one prediction destroyed,
and the surviving text describing an SQL filter while "Also at:" named the
payment file.

Nothing recorded it. A collapsed finding entered no list, so the count of
things the reviewer said dropped by three and `falsifiable_precision` -- which
divides by findings plus discarded -- rose 8.5x with no change to the reviewer.
"""

from __future__ import annotations

from augury.core.findings import Finding, Severity
from augury.core.repetition import collapse


def _finding(path: str, mechanism: str, severity: Severity = Severity.MEDIUM) -> Finding:
    return Finding(
        path=path,
        line=1,
        layer="security",
        symbol=path.replace("/", "_").replace(".py", ""),
        mechanism=mechanism,
        remediation="fix it",
        severity=severity,
    )


_SHARED = "The handler does not validate the request body before"


def test_four_different_bugs_sharing_a_clause_stay_four_findings() -> None:
    kept, _ = collapse(
        [
            _finding("a.py", f"{_SHARED} building the SQL filter."),
            _finding("b.py", f"{_SHARED} writing it to the audit log."),
            _finding("c.py", f"{_SHARED} forwarding it to the payment provider.", Severity.HIGH),
            _finding("d.py", f"{_SHARED} caching it for every tenant.", Severity.HIGH),
        ]
    )

    assert len(kept) == 4


def test_a_mechanism_that_is_all_identifiers_is_never_collapsed() -> None:
    """Stripping specifics left the empty shape, which matched everything.

    Three unrelated defects became one finding announcing itself as "a property
    of the service rather than of one handler".
    """
    kept, _ = collapse(
        [
            _finding("a.py", "`open(...).read()` `1.5MB` `sync_io`"),
            _finding("b.py", "`psycopg2.connect` `db.pool` `2.0s`"),
            _finding("c.py", "`hashlib.pbkdf2_hmac` `100000` `rounds`"),
        ]
    )

    assert len(kept) == 3


def test_the_same_bug_in_three_files_is_still_collapsed() -> None:
    """The behaviour this exists for, which must survive the fix."""
    same = "The handler does not propagate the correlation id to the downstream call."
    kept, dropped = collapse([_finding(f"{n}.py", same) for n in "abc"])

    assert len(kept) == 1
    assert "Seen in 3 files" in kept[0].mechanism
    assert len(dropped) == 2, "the two it stood in for have to be recorded"


def test_what_was_collapsed_away_is_recorded_rather_than_deleted() -> None:
    """A finding in neither `findings` nor `dropped` is one nobody can audit."""
    same = "The handler does not propagate the correlation id to the downstream call."
    kept, dropped = collapse([_finding(f"{n}.py", same) for n in "abc"])

    assert len(kept) + len(dropped) == 3
    assert all("collapsed" in entry.reason for entry in dropped)


def test_the_survivor_carries_the_worst_severity_it_stood_in_for() -> None:
    """It took the alphabetically first path's severity, which is not a ranking."""
    same = "The handler does not propagate the correlation id to the downstream call."
    kept, _ = collapse(
        [
            _finding("a.py", same, Severity.LOW),
            _finding("b.py", same, Severity.HIGH),
            _finding("c.py", same, Severity.LOW),
        ]
    )

    assert kept[0].severity is Severity.HIGH
