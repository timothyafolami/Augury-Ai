"""The memo must not answer while a cassette is being recorded.

The memo cache sits above the cassette layer, keyed by the absolute
repository path under the user's cache directory. Recording a run on a
machine with a warm memo writes a cassette only for the calls the memo
happened to miss, and the resulting set replays on exactly that machine and
nowhere else.

Found by cloning the repository and running `make demo` with no key: the
clone made 32 cassette lookups and missed all 32, while the same review here
made 7 and hit all 7. The other 25 answers came from ~/.cache/augury.

The memo saves money on repeat live runs. During a recording, a complete
cassette set is worth more than the saving, so the memo stands down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.cli.main import _memo_for as cli_memo_for
from augury.core.drafts import DraftReport
from augury.server.app import _memo_for as server_memo_for


def _seed(root: Path, monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """Write one entry the way an ordinary live run would."""
    monkeypatch.delenv("AUGURY_RECORD", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    warm = server_memo_for(root, model_id="m")
    warm.remember("src", "data", "python", "prompt", DraftReport(findings=[]))
    assert warm.recall("src", "data", "python", "prompt") is not None, "seed did not take"


def test_the_cli_memo_stands_down_while_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    _seed(tmp_path, monkeypatch, cache)
    monkeypatch.setenv("AUGURY_RECORD", "1")

    memo = cli_memo_for(tmp_path, enabled=True, model_id="m")

    assert memo.recall("src", "data", "python", "prompt") is None
    assert memo.hits == 0


def test_the_server_memo_stands_down_while_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    _seed(tmp_path, monkeypatch, cache)
    monkeypatch.setenv("AUGURY_RECORD", "1")

    memo = server_memo_for(tmp_path, model_id="m")

    assert memo.recall("src", "data", "python", "prompt") is None
    assert memo.hits == 0


def test_a_memo_that_stood_down_records_nothing_either(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Otherwise the next run reads entries written under a shadowed key."""
    monkeypatch.setenv("AUGURY_RECORD", "1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    memo = server_memo_for(tmp_path, model_id="m")
    memo.remember("src", "data", "python", "prompt", DraftReport(findings=[]))

    assert memo.recall("src", "data", "python", "prompt") is None


def test_the_memo_still_answers_when_nothing_is_being_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The saving is the point of the cache; only recording suspends it."""
    cache = tmp_path / "cache"
    _seed(tmp_path, monkeypatch, cache)

    memo = server_memo_for(tmp_path, model_id="m")

    assert memo.recall("src", "data", "python", "prompt") is not None


def test_a_memo_never_asks_for_full_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reading one flag must not drag in the provider-key check.

    The keyless replay path is the one this fix exists to protect, and full
    settings refuse to load without a provider key. A memo that asked for
    them would turn "no key" into a crash on the way to a free run. Asserted
    by making the full load fail: a memo that touches it fails with it.
    """
    import augury.core.memo as memo_module

    def refuse() -> None:
        raise AssertionError("the memo loaded full settings")

    monkeypatch.setattr(memo_module, "load_settings", refuse, raising=False)
    monkeypatch.setattr("augury.core.settings.load_settings", refuse)
    monkeypatch.setenv("AUGURY_RECORD", "1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    memo = server_memo_for(tmp_path, model_id="m")

    assert memo.recall("src", "data", "python", "prompt") is None


def test_the_memo_stands_down_while_replaying_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Replay reproduces one recorded run, and a cache above it can disagree.

    Measured, not supposed. The same web review of the same repository against
    the same cassettes returned 16 findings, 5 pressures and a 259-line
    document with a cold memo, and 10 findings, 4 pressures and 207 lines with
    a warm one. The memo had been filled by live runs whose answers differed
    from the recording, and being the outer layer it won.

    So the published numbers held only on a machine that had never run this
    before, which is the opposite of what a committed recording is for.

    The memo is an optimisation for live runs. Recording bypasses it so the
    cassette set is complete; replay bypasses it so the cassette set is what
    answers.
    """
    cache = tmp_path / "cache"
    _seed(tmp_path, monkeypatch, cache)
    monkeypatch.setenv("AUGURY_REPLAY_ONLY", "1")

    memo = server_memo_for(tmp_path, model_id="m")

    assert memo.recall("src", "data", "python", "prompt") is None
    assert memo.hits == 0
