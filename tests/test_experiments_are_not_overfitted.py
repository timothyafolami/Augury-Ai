"""An experiment must detect the defect, not one particular fix for it.

`tests/test_experiments_discriminate.py` compares the seeded repository with
one remediation, which is necessary and not sufficient: `queue_depth` passed
that test while reporting the identical number for an unbounded queue and one
bounded at 512, because the shipped fix happened to bound it at 32 and 32 was
below the arithmetic the harness constants produced.

So each defect that can be fixed more than one way is checked against more than
one fix.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CASES = Path(__file__).parent.parent / "eval" / "cases"


def measure(case: Path, metric: str, repo: Path) -> float | None:
    result = subprocess.run(
        [sys.executable, str(case / "experiments" / f"{metric}.py")],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "AUGURY_CASE_REPO": str(repo)},
    )
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return float(line.strip())
        except ValueError:
            continue
    return None


def patched(case: Path, tmp_path: Path, relative: str, old: str, new: str) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(case / "repo", repo)
    target = repo / relative
    source = target.read_text()
    assert old in source, f"{relative} no longer contains the text this test patches"
    target.write_text(source.replace(old, new))
    return repo


@pytest.mark.parametrize("bound", [32, 512, 4096])
def test_queue_depth_detects_any_bound_not_one_particular_bound(tmp_path: Path, bound: int) -> None:
    case = CASES / "C01-notifications"
    seeded = measure(case, "queue_depth", case / "repo")
    repo = patched(
        case,
        tmp_path,
        "app/queue/inbox.py",
        "asyncio.Queue()",
        f"asyncio.Queue(maxsize={bound})",
    )

    assert measure(case, "queue_depth", repo) != seeded


LEAK = (
    "    session = SessionLocal()\n"
    "    result = await work(session)  # type: ignore[operator]\n"
    "    await session.close()\n"
    "    return result"
)

RELEASES = {
    "try/finally": (
        "    session = SessionLocal()\n"
        "    try:\n"
        "        return await work(session)  # type: ignore[operator]\n"
        "    finally:\n"
        "        await session.close()"
    ),
    "context manager": (
        "    async with SessionLocal() as session:\n"
        "        return await work(session)  # type: ignore[operator]"
    ),
}


@pytest.mark.parametrize("style", sorted(RELEASES))
def test_the_leak_is_detected_however_the_session_is_released(tmp_path: Path, style: str) -> None:
    case = CASES / "C01-notifications"
    seeded = measure(case, "active_connections", case / "repo")
    repo = patched(case, tmp_path, "app/store/session.py", LEAK, RELEASES[style])

    assert measure(case, "active_connections", repo) != seeded
