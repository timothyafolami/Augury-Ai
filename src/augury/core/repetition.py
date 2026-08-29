"""One defect reported many times is one defect.

"Correlation identifiers are not propagated" is true of a service rather than
of a file, so a per-file reviewer reports it once per file it reads. On a real
run that was sixteen of a hundred and forty-one findings saying one sentence
about sixteen route handlers.

Collapsing is not hiding. The finding is kept with every location it was seen
at, and the count becomes the evidence that it is systemic. What it stops is
one observation occupying sixteen lines of a list somebody has to triage.
"""

from __future__ import annotations

import re
from collections import defaultdict

from augury.core.findings import Finding

# Below this, a repeat is a coincidence. At it, the finding is about the
# service. Declared rather than judged per report.
SYSTEMIC_FILES = 3

# Identifiers, paths and numbers are what differ between two reports of one
# systemic defect: the specialist names the symbol it was looking at.
_SPECIFICS = re.compile(
    "|".join(
        (
            r"`[^`]*`",  # anything the specialist quoted
            r"\b[A-Za-z_][A-Za-z0-9_]*[/.][A-Za-z0-9_./]*",  # dotted or pathed
            r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b",  # snake_case: a symbol, unquoted
            r"\b\d[\d.,]*\b",  # any number
        )
    )
)
_WORD = re.compile(r"[a-z]+")

# Words that carry the mechanism. Dropping the rest is what lets "list_orders
# does not propagate a correlation id" and the same sentence about list_users
# be recognised as one finding.
_SHAPE_WORDS = 8


def collapse(findings: list[Finding]) -> list[Finding]:
    """Merge findings that say the same thing about different files."""
    groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[(finding.layer, _shape(finding.mechanism))].append(finding)

    merged: list[Finding] = []
    for group in groups.values():
        files = {f.path for f in group}
        if len(files) < SYSTEMIC_FILES:
            merged.extend(group)
            continue
        merged.append(_one_of(group, files))
    return merged


def _shape(mechanism: str) -> str:
    """What a sentence says with its specifics removed."""
    without = _SPECIFICS.sub(" ", mechanism.lower())
    words = _WORD.findall(without)
    return " ".join(words[:_SHAPE_WORDS])


def _one_of(group: list[Finding], files: set[str]) -> Finding:
    """The first finding, carrying everywhere else it was seen."""
    first = min(group, key=lambda f: f.path)
    others = sorted(files - {first.path})
    shown = ", ".join(others[:5]) + (", ..." if len(others) > 5 else "")
    return first.model_copy(
        update={
            "mechanism": (
                f"{first.mechanism} Seen in {len(files)} files, so this is a property "
                f"of the service rather than of one handler. Also at: {shown}"
            )
        }
    )
