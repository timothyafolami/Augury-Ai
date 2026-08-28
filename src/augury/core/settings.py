"""Where the run gets its model, its key and its mode.

Model choice is configuration because the same evaluation run on two sizes of
the same model family is how we find out whether a result depends on model
capability or on the architecture around it. That question cannot be answered
if the model is an edit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast, get_args

from pydantic import BaseModel, ConfigDict

from augury.core.adapters.base import ModelSpec, Provider
from augury.core.adapters.pricing import pricing_for

# Only these may be set from a .env file. Augury is pointed at repositories it
# does not trust, and `cd untrusted-repo && augury review .` is the obvious
# invocation, so an unrestricted loader would let a reviewed repository set
# GIT_CONFIG_*, LD_PRELOAD, or simply AUGURY_REPLAY_ONLY=1 to escape review.
DOTENV_ALLOWED = frozenset(
    {
        "AUGURY_PROVIDER",
        "AUGURY_MODEL",
        "AUGURY_TEMPERATURE",
        "AUGURY_REPLAY_ONLY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }
)

DEFAULT_PROVIDER = "groq"
DEFAULT_MODEL = "openai/gpt-oss-120b"

API_KEY_VARIABLES: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class SettingsError(Exception):
    """The environment does not describe a runnable configuration."""


class Settings(BaseModel):
    """Everything a run needs that is not a command-line argument."""

    model_config = ConfigDict(frozen=True)

    spec: ModelSpec
    api_key: str
    replay_only: bool


def load_settings() -> Settings:
    """Read the environment, refusing anything that cannot produce a real run."""
    _load_dotenv()

    name = os.environ.get("AUGURY_PROVIDER", DEFAULT_PROVIDER)
    if name not in get_args(Provider):
        raise SettingsError(
            f"AUGURY_PROVIDER={name!r} is not supported. "
            f"Choose one of: {', '.join(get_args(Provider))}"
        )
    provider = cast("Provider", name)

    model = os.environ.get("AUGURY_MODEL", DEFAULT_MODEL)
    try:
        pricing_for(model)
    except KeyError as exc:
        raise SettingsError(str(exc.args[0])) from exc

    replay_only = os.environ.get("AUGURY_REPLAY_ONLY", "") not in ("", "0", "false")

    return Settings(
        spec=ModelSpec(
            provider=provider,
            model=model,
            temperature=_temperature(),
            max_tokens=_max_tokens(),
        ),
        # Replay serves recorded answers, so it must work with no key at all.
        # That is the path a judge takes.
        api_key="" if replay_only else _api_key(provider),
        replay_only=replay_only,
    )


def _dotenv_path() -> Path:
    """Augury's own .env, never the reviewed repository's.

    Anchored to the installation rather than the working directory: the working
    directory is frequently a repository under review, and its .env is written
    by whoever wrote the code we are supposed to be judging.
    """
    override = os.environ.get("AUGURY_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent.parent / ".env"


def _load_dotenv(path: Path | None = None) -> None:
    """Fill in the variables .env declares that the environment does not set.

    A real environment variable always wins: CI sets real ones, and a stale
    .env silently overriding them is a debugging afternoon nobody enjoys.

    Only names in DOTENV_ALLOWED are honoured. Everything else is ignored
    rather than exported, because this file may not be ours.
    """
    env_file = path or _dotenv_path()
    if not env_file.is_file():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, value = _parse_dotenv_line(line)
        if name in DOTENV_ALLOWED:
            os.environ.setdefault(name, value)


def _parse_dotenv_line(line: str) -> tuple[str, str]:
    """One `NAME=value` line, or an empty name when there is nothing to set.

    Handles the three forms that silently misconfigured a run: an `export`
    prefix, an inline `# comment` after an unquoted value, and quotes used as
    delimiters rather than stripped as a character class.
    """
    stripped = line.strip().removeprefix("export ").strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return "", ""

    name, _, raw = stripped.partition("=")
    value = raw.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return name.strip(), value[1:-1]

    # Unquoted values end at an inline comment. A key with a trailing
    # "  # prod" is non-empty, so it passes the presence check and then fails
    # authentication with an opaque 401.
    return name.strip(), value.split(" #", 1)[0].strip()


def _api_key(provider: str) -> str:
    variable = API_KEY_VARIABLES[provider]
    key = os.environ.get(variable, "")
    if not key:
        raise SettingsError(
            f"{variable} is not set. Export it, or set AUGURY_REPLAY_ONLY=1 to "
            "replay recorded runs without a key."
        )
    return key


def _max_tokens() -> int:
    """Room for a reasoning model to think and then answer."""
    raw = os.environ.get("AUGURY_MAX_TOKENS", "16000")
    try:
        return int(raw)
    except ValueError as exc:
        raise SettingsError(f"AUGURY_MAX_TOKENS={raw!r} is not a whole number") from exc


def _temperature() -> float:
    """Zero unless deliberately raised: a review should not vary run to run."""
    raw = os.environ.get("AUGURY_TEMPERATURE", "0")
    try:
        return float(raw)
    except ValueError as exc:
        raise SettingsError(f"AUGURY_TEMPERATURE={raw!r} is not a number") from exc
