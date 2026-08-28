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
        spec=ModelSpec(provider=provider, model=model, temperature=_temperature()),
        # Replay serves recorded answers, so it must work with no key at all.
        # That is the path a judge takes.
        api_key="" if replay_only else _api_key(provider),
        replay_only=replay_only,
    )


def _load_dotenv(path: Path | None = None) -> None:
    """Fill in anything .env declares that the environment does not already set.

    A real environment variable always wins: CI sets real ones, and a stale
    .env silently overriding them is a debugging afternoon nobody enjoys.
    """
    env_file = path or Path.cwd() / ".env"
    if not env_file.is_file():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def _api_key(provider: str) -> str:
    variable = API_KEY_VARIABLES[provider]
    key = os.environ.get(variable, "")
    if not key:
        raise SettingsError(
            f"{variable} is not set. Export it, or set AUGURY_REPLAY_ONLY=1 to "
            "replay recorded runs without a key."
        )
    return key


def _temperature() -> float:
    """Zero unless deliberately raised: a review should not vary run to run."""
    raw = os.environ.get("AUGURY_TEMPERATURE", "0")
    try:
        return float(raw)
    except ValueError as exc:
        raise SettingsError(f"AUGURY_TEMPERATURE={raw!r} is not a number") from exc
