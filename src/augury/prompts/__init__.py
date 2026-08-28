"""Load the instructions that shape each agent.

Prompts are markdown files rather than string literals so they can be reviewed,
diffed, and cited by the improvement changelog when a prompt change is the
cause of a measured delta. A prompt that renders with a variable missing is an
error, because shipping the characters `{module}` to a model is a quality
failure that reads like a bad model rather than a bug.
"""

from __future__ import annotations

from functools import cache
from string import Formatter
from pathlib import Path

_DIRECTORY = Path(__file__).parent
_SUFFIX = ".md"


class PromptError(Exception):
    """A prompt is missing, or a variable it needs was not supplied."""


@cache
def available() -> tuple[str, ...]:
    """Every prompt name on disk, including layer briefs as `layer/<name>`."""
    return tuple(
        sorted(
            path.relative_to(_DIRECTORY).with_suffix("").as_posix()
            for path in _DIRECTORY.rglob(f"*{_SUFFIX}")
        )
    )


def raw(name: str) -> str:
    """The unrendered text of a prompt."""
    path = _DIRECTORY / f"{name}{_SUFFIX}"
    if not path.is_file():
        raise PromptError(f"no prompt named {name!r}. Available: {', '.join(available())}")
    return path.read_text(encoding="utf-8")


def render(name: str, **variables: object) -> str:
    """Fill a prompt's placeholders, refusing to leave any unfilled."""
    try:
        return Formatter().vformat(raw(name), (), _NoSilentDefaults(variables))
    except KeyError as exc:
        raise PromptError(
            f"prompt {name!r} needs a value for {exc.args[0]!r}, which was not supplied"
        ) from exc


class _NoSilentDefaults(dict[str, object]):
    """A mapping with no default, so an unfilled placeholder raises."""

    def __missing__(self, key: str) -> object:
        raise KeyError(key)
