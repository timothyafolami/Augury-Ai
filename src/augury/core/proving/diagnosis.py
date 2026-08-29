"""Turning a failed experiment into a sentence somebody can act on.

Proving three findings on a real repository returned "broken: printed no
number" three times. The cause was one line of stderr -- `ModuleNotFoundError:
No module named 'jwt'` -- because that repository's dependencies live in the
Docker image its compose file builds and no local interpreter has them.

Both sentences are true. Only one of them tells the reader what to do.
"""

from __future__ import annotations

import re

_MISSING_MODULE = re.compile(r"No module named ['\"]([\w.]+)['\"]")
_SYNTAX = re.compile(r"^\s*SyntaxError:", re.MULTILINE)


def diagnose(stderr: str, *, interpreter: str) -> str:
    """Why the experiment did not produce a measurement."""
    if not stderr.strip():
        return "no error output, and no number printed"

    if _SYNTAX.search(stderr):
        return f"the generated script does not parse: {_tail(stderr)}"

    missing = _MISSING_MODULE.search(stderr)
    if missing is not None:
        module = missing.group(1)
        top = module.split(".")[0]
        # A dotted name usually belongs to the repository; a bare one usually
        # comes from its dependencies. Not certain, so both are hedged.
        if "." in module:
            return (
                f"`{module}` was not importable under {interpreter}. That looks like "
                "part of the repository rather than a dependency, so the experiment "
                "was run from the wrong path"
            )
        return (
            f"`{top}` is not installed in {interpreter}. The repository's "
            "dependencies are not available to any interpreter found beside it -- "
            "if its services build from a Dockerfile, they live in the image and "
            "an experiment cannot import them here"
        )

    return _tail(stderr)


def _tail(text: str, lines: int = 2) -> str:
    return " / ".join(text.strip().splitlines()[-lines:])
