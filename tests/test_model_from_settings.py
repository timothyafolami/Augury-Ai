"""Every entrypoint builds its model the same way, or replay silently breaks.

`build_model` takes a spec and a key, so a caller that forgets replay mode gets
a live client and spends money. That has already happened once in this project
with experiment conditions: three call sites, one updated, a green suite, and a
published number produced by a command nobody had run. The fix is not vigilance
-- it is a single function that takes `Settings`, plus a test that fails when
anyone reaches past it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from augury.core.adapters.base import ModelSpec
from augury.core.adapters.cassette import CassetteMiss, CassetteModel
from augury.core.adapters.provider import ProviderAdapter, model_from
from augury.core.settings import Settings

SRC = Path(__file__).resolve().parent.parent / "src" / "augury"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "spec": ModelSpec(provider="groq", model="openai/gpt-oss-120b"),
        "api_key": "test-key",
        "replay_only": False,
        "record": False,
        "cassette_dir": None,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_a_normal_run_gets_the_live_adapter_and_no_cassette() -> None:
    model = model_from(_settings())
    assert isinstance(model, ProviderAdapter)


def test_replay_wraps_the_adapter_in_a_cassette(tmp_path: Path) -> None:
    model = model_from(_settings(replay_only=True, api_key="", cassette_dir=tmp_path))
    assert isinstance(model, CassetteModel)


def test_replay_against_a_missing_cassette_directory_says_so(tmp_path: Path) -> None:
    # The failure a judge hits if they clone without the recordings. It must
    # name the directory, not fall back to spending money.
    with pytest.raises(CassetteMiss, match="does not exist"):
        model_from(_settings(replay_only=True, api_key="", cassette_dir=tmp_path / "absent"))


def test_recording_wraps_the_adapter_too(tmp_path: Path) -> None:
    model = model_from(_settings(record=True, cassette_dir=tmp_path))
    assert isinstance(model, CassetteModel)


def test_replay_needs_no_api_key() -> None:
    # load_settings blanks the key in replay mode; building must not object.
    assert model_from(_settings(replay_only=True, api_key="", cassette_dir=Path.cwd()))


def test_no_module_outside_the_provider_calls_build_model_directly() -> None:
    """The enforcement. `model_from` is the only supported way in."""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name == "provider.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "build_model":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == [], (
        "These call build_model directly and so ignore replay mode. "
        f"Use model_from(settings) instead: {offenders}"
    )
