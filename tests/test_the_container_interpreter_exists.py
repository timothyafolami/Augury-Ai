"""The experiment runs under an interpreter the image actually has.

`docker compose run ... python /tmp/augury-experiment.py` assumes a bare
`python` on the container's PATH. Debian and Ubuntu stopped providing one
years ago: they ship `python3` and no unversioned alias. `golang:1.22` was
probed directly for this test and has `/usr/bin/python3` and no `python`, so
every experiment against a Go service died as BROKEN with an exec failure
that named the script rather than the missing interpreter.

Found by adding the first non-Python case to the evaluation suite. No Python
case could reach it: their images are `python:*`, which do provide the alias.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.proving.environment import MOUNT_POINT, Environment


def _compose() -> Environment:
    return Environment(kind="compose", root=Path("/repo"), service="api")


def test_the_command_does_not_assume_an_unversioned_python() -> None:
    command = _compose().command(Path("/tmp/x.py"))

    assert "python" not in command, (
        "a bare `python` is absent from Debian-based images, which is most of them"
    )


def test_the_command_prefers_python3_and_falls_back() -> None:
    """An image with only `python` is old, not impossible. Both are tried."""
    joined = " ".join(_compose().command(Path("/tmp/x.py")))

    assert "python3" in joined
    assert "python " in joined or joined.endswith("python")


def test_the_script_is_still_the_mounted_one() -> None:
    joined = " ".join(_compose().command(Path("/tmp/x.py")))

    assert MOUNT_POINT in joined
    assert joined.count(MOUNT_POINT) >= 1


def test_a_local_run_is_unchanged() -> None:
    """Only the container path was guessing. A local run names its interpreter."""
    where = Environment(kind="local", root=Path("/repo"), python=Path("/usr/bin/python3.12"))

    assert where.command(Path("/tmp/x.py")) == ["/usr/bin/python3.12", "/tmp/x.py"]
