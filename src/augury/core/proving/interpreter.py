"""Finding the Python a repository actually runs on.

A generated experiment imports the code it measures. Run with Augury's own
interpreter it fails at the first third-party import -- `jwt`, `fastapi`,
`sqlalchemy` -- because those dependencies belong to the repository under
review. Every proof then comes back "printed no number", which is true and
tells nobody anything.

Most repositories ship their interpreter. Using it is the difference between an
experiment that measures the claim and one that measures our virtualenv.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# In the order people create them. `.conda` is here because the first real
# repository this ran against used it, and it is the one layout that would have
# been missed by guessing.
ENVIRONMENTS = (".venv", "venv", ".conda", "env", ".virtualenv", ".env")

# Where an interpreter sits inside one, POSIX and Windows.
BIN_PATHS = (("bin", "python"), ("bin", "python3"), ("Scripts", "python.exe"))


def interpreter_for(root: Path) -> Path:
    """The repository's own Python, or ours if it has none.

    Falls back rather than refusing: a script that imports nothing third-party
    still runs, and refusing would turn a measurable claim into an unmeasurable
    one for the sake of tidiness.
    """
    base = Path(root)
    for environment in ENVIRONMENTS:
        for parts in BIN_PATHS:
            candidate = base / environment / Path(*parts)
            # Executable, not merely present: a stale directory left behind by
            # a deleted virtualenv is not an interpreter.
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return Path(sys.executable)
