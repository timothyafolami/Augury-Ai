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

from augury.core.findings import Dropped, Finding, Severity

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

# A shape shorter than this is not evidence of sameness. A mechanism made
# entirely of quoted identifiers and numbers reduced to the empty shape, which
# matched every other such mechanism, so three unrelated defects became one
# finding announcing itself as "a property of the service".
_ENOUGH_TO_COMPARE = 5


def collapse(findings: list[Finding]) -> tuple[list[Finding], list[Dropped]]:
    """Merge findings that say the same thing about different files.

    Returns what survives and what it stood in for. A finding that is in
    neither list is one nobody can audit -- and it also leaves the denominator
    of falsifiable precision, which counts findings plus discarded, so merging
    on one arm lifted that arm's score by up to 8.5x with no change to the
    reviewer.
    """
    groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    alone: list[Finding] = []
    for finding in findings:
        shape = _shape(finding.mechanism)
        # Too little left to compare. Grouping on it merges by coincidence.
        if len(shape.split()) < _ENOUGH_TO_COMPARE:
            alone.append(finding)
            continue
        groups[(finding.layer, shape)].append(finding)

    merged: list[Finding] = list(alone)
    stood_in_for: list[Dropped] = []
    for group in groups.values():
        files = {f.path for f in group}
        if len(files) < SYSTEMIC_FILES:
            merged.extend(group)
            continue
        survivor = _one_of(group, files)
        merged.append(survivor)
        stood_in_for.extend(
            Dropped(
                symbol=other.symbol,
                path=other.path,
                reason=(
                    f"collapsed into the same finding at {survivor.path}: the same "
                    f"mechanism in {len(files)} files is one property of the service"
                ),
            )
            for other in group
            if other is not survivor_source(group)
        )
    return merged, stood_in_for


def survivor_source(group: list[Finding]) -> Finding:
    """Which finding the merged one was built from."""
    # Worst severity first, then the earliest path, so the choice is stable
    # across runs and unchanged from before when the severities agree.
    return min(group, key=lambda f: (-_WEIGHT[f.severity], f.path))


def _shape(mechanism: str) -> str:
    """What a sentence says with its specifics removed.

    The whole sentence, not a prefix of it. Keeping the first eight words
    grouped four handlers that "do not validate the request body before ..."
    doing four different things with it -- and the ninth word is where the
    mechanism lives.
    """
    without = _SPECIFICS.sub(" ", mechanism.lower())
    return " ".join(_WORD.findall(without))


def _one_of(group: list[Finding], files: set[str]) -> Finding:
    """The most serious finding, carrying everywhere else it was seen.

    The alphabetically first was taken before, which is not a ranking: a MEDIUM
    in `a.py` silently replaced two HIGHs, and the severity a reader acts on
    became a fact about filenames.
    """
    first = survivor_source(group)
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


# Ordering severities so the survivor of a merge is the worst of what it
# stands for, rather than whichever file sorts first.
_WEIGHT = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}
