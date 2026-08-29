"""Withdrawing index claims the repository already answers.

A specialist is shown one file. "This column has no index" is a statement about
a different file -- the model definition, or a migration -- so the specialist is
guessing, and on a real repository it guessed wrong twice in the top ten
findings, complete with an invented row count.

The harness has already parsed the migrations. A claim the parsed schema
settles should not reach a human as an open question, which is the same
argument as the falsifiability gate one layer along: check what can be checked,
deterministically, before publishing.

Only withdraws. A column this cannot prove indexed is left alone, because an
absent migration is not evidence of an absent index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from augury.core.findings import Finding
from augury.core.schema.model import Operation

# The claim this can settle, in the spellings specialists actually write.
_CLAIMS_NO_INDEX = re.compile(
    r"\b(?:without|no|missing|lacks?|absent|not)\b[^.]{0,40}\bindex", re.IGNORECASE
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Withdrawn:
    """A finding removed because the repository contradicts it."""

    finding: Finding
    reason: str


class IndexedColumns:
    """Which (table, column) pairs the migrations index."""

    def __init__(self, pairs: set[tuple[str, str]]) -> None:
        self._pairs = pairs

    def __contains__(self, pair: object) -> bool:
        return pair in self._pairs

    def __bool__(self) -> bool:
        return bool(self._pairs)

    def covering(self, words: set[str]) -> tuple[str, str] | None:
        """A pair whose table and column are both named in this text."""
        return next(
            ((t, c) for (t, c) in self._pairs if t in words and c in words),
            None,
        )


def indexed_columns(operations: tuple[Operation, ...]) -> IndexedColumns:
    """Every column the migrations put an index on."""
    return IndexedColumns(
        {
            (op.table, column)
            for op in operations
            if op.kind in {"create_index", "create_unique_constraint"}
            for column in op.columns
        }
    )


def withdraw_false_index_claims(
    findings: list[Finding], indexed: IndexedColumns
) -> tuple[list[Finding], list[Withdrawn]]:
    """Split findings into those that survive the schema and those that do not."""
    if not indexed:
        # No migrations read. Knowing of no index is not knowing there is none.
        return list(findings), []

    kept: list[Finding] = []
    withdrawn: list[Withdrawn] = []
    for finding in findings:
        pair = _contradicted(finding, indexed)
        if pair is None:
            kept.append(finding)
            continue
        table, column = pair
        withdrawn.append(
            Withdrawn(
                finding=finding,
                reason=(
                    f"{table}.{column} is indexed by a migration in this repository, "
                    "so the finding's premise is false"
                ),
            )
        )
    return kept, withdrawn


def _contradicted(finding: Finding, indexed: IndexedColumns) -> tuple[str, str] | None:
    """The claim lives in the mechanism, so only the mechanism is read.

    Reading the remediation as well finds the column it recommends indexing,
    which is a different column from the one the claim is about as often as not
    -- and withdrawing a true finding because its fix names an indexed column
    is worse than leaving a false one in.
    """
    if not _CLAIMS_NO_INDEX.search(finding.mechanism):
        return None
    words = {word.lower() for word in _IDENTIFIER.findall(finding.mechanism)}
    return indexed.covering(words)
