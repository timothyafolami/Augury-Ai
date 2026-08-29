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


# The module allowed to call build_model, by full path rather than by basename:
# exempting every file merely *named* provider.py exempts one someone adds later.
PROVIDER = SRC / "core" / "adapters" / "provider.py"

# Scanned beyond src/, because an eval script that reaches past model_from
# spends real money in a run the operator believes is replayed.
SCANNED = (SRC, SRC.parent.parent / "tests", SRC.parent.parent / "eval")

# The only files allowed to call build_model directly, each for a stated
# reason. A name added here is a decision; a name matched by pattern is not.
ALLOWED = {
    # The unit tests for build_model itself, which must call the thing they test.
    "test_provider_adapter.py",
    # This file, which calls it inside a fixture to prove the check works.
    "test_model_from_settings.py",
}


def _direct_build_model_calls(path: Path) -> list[str]:
    """Every direct call to build_model in one file, however it is spelled."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    aliases = {"build_model"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases |= {a.asname or a.name for a in node.names if a.name == "build_model"}

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        named = isinstance(func, ast.Name) and func.id in aliases
        # provider.build_model(...) -- an Attribute, previously invisible.
        attributed = isinstance(func, ast.Attribute) and func.attr == "build_model"
        if named or attributed:
            found.append(f"{path}:{node.lineno}")
    return found


def test_nothing_outside_the_provider_calls_build_model_directly() -> None:
    """The enforcement. `model_from` is the only supported way in."""
    offenders: list[str] = []
    for directory in SCANNED:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            if path.resolve() == PROVIDER.resolve() or path.name in ALLOWED:
                continue
            offenders.extend(_direct_build_model_calls(path))
    assert offenders == [], (
        "These call build_model directly and so ignore replay mode. "
        f"Use model_from(settings) instead: {offenders}"
    )


def test_the_sealed_model_refuses_every_call() -> None:
    """The guarantee replay exists to give, asserted rather than documented.

    A mutant returning `schema.model_construct()` from these two methods left
    all 465 tests green: nothing constructed SealedModel, so nothing noticed
    replay could fabricate empty answers at $0.00 and be indistinguishable from
    a correct free reproduction. That is the mock-that-lies shape, at the one
    place this project has already been burned by it.
    """
    import asyncio

    from augury.core.adapters.provider import SealedModel

    sealed = SealedModel("some-model")
    assert sealed.model_id == "some-model"
    assert sealed.usage.usd == 0.0

    for coroutine in (
        sealed.structured(prompt="p", schema=ModelSpec),
        sealed.call(prompt="p", schema=ModelSpec),
    ):
        with pytest.raises(CassetteMiss, match="no recording covers this call"):
            asyncio.run(coroutine)


def test_replay_seals_the_model_inside_the_cassette(tmp_path: Path) -> None:
    """Asserting the wrapper is a CassetteModel says nothing about its inside."""
    from augury.core.adapters.provider import SealedModel

    model = model_from(_settings(replay_only=True, api_key="", cassette_dir=tmp_path))
    assert isinstance(model, CassetteModel)
    assert isinstance(model._inner, SealedModel)


def test_a_qualified_or_aliased_call_is_caught_too(tmp_path: Path) -> None:
    """The enforcement test missed the two ways the mistake is actually written.

    `provider.build_model(...)` is an ast.Attribute and an aliased import
    renames the ast.Name; both were invisible to a check that matched only a
    bare name. A probe module written exactly that way passed the suite.
    """
    module = tmp_path / "escape.py"
    module.write_text(
        "from augury.core.adapters import provider\n"
        "from augury.core.adapters.provider import build_model as bm\n\n\n"
        "def a():\n    return provider.build_model(spec, api_key='k')\n\n\n"
        "def b():\n    return bm(spec, api_key='k')\n"
    )
    assert len(_direct_build_model_calls(module)) == 2
