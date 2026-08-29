"""Running a generated experiment, and refusing to over-read the result."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import mkdtemp

from augury.core.findings import Finding
from augury.core.proving.diagnosis import diagnose
from augury.core.proving.environment import Environment
from augury.core.proving.interpreter import interpreter_for
from augury.core.proving.model import Experiment, Proof
from augury.core.schemas import Outcome

# Long enough for a load loop, short enough that a hung script does not hold a
# review open. An experiment that needs longer is one nobody will run twice.
DEFAULT_TIMEOUT = 90.0

Generator = Callable[[Finding, Path], Awaitable[Experiment]]

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


async def prove_finding(
    finding: Finding,
    *,
    root: Path,
    generate: Generator,
    timeout: float = DEFAULT_TIMEOUT,
    workspace: Path | None = None,
    environment: Environment | None = None,
) -> Proof | None:
    """Generate an experiment for this finding, run it, and grade it.

    None when the finding carries no prediction: there is nothing to measure,
    so nothing is generated and nothing is run.
    """
    prediction = finding.prediction
    if prediction is None:
        return None

    experiment = await generate(finding, root)

    # Written before it runs. Whatever the verdict, someone has to be able to
    # read what executed against their repository.
    directory = Path(workspace or mkdtemp(prefix="augury-proof-"))
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / f"{finding.symbol or 'experiment'}.py"
    script.write_text(experiment.source, encoding="utf-8")

    # Where the code under review can actually be imported: the image its
    # service is built from, or an interpreter beside the repository. Ours has
    # none of the dependencies under review.
    where = environment or Environment(kind="local", root=root, python=interpreter_for(root))

    started = time.monotonic()
    code, stdout, stderr = await _run(script, root, timeout, where)
    elapsed = time.monotonic() - started

    if code is None:
        return Proof(
            measured=None,
            outcome=Outcome.BROKEN,
            detail=f"timed out after {timeout:g}s",
            script_path=str(script),
            seconds=elapsed,
        )
    if code != 0:
        return Proof(
            measured=None,
            outcome=Outcome.BROKEN,
            detail=diagnose(stderr, interpreter=where.describes),
            script_path=str(script),
            seconds=elapsed,
        )

    measured = _last_number(stdout)
    if measured is None:
        # Silence is not zero. An experiment that printed no number measured
        # nothing, and grading it against the prediction would invent a result.
        return Proof(
            measured=None,
            outcome=Outcome.BROKEN,
            detail=(
                f"printed no number under {where.describes}: "
                f"{diagnose(stderr, interpreter=where.describes)}"
            ),
            script_path=str(script),
            seconds=elapsed,
        )

    return Proof(
        measured=measured,
        outcome=prediction.score(measured),
        detail=experiment.explanation,
        script_path=str(script),
        seconds=elapsed,
    )


async def _run(
    script: Path, root: Path, timeout: float, where: Environment
) -> tuple[int | None, str, str]:
    """Execute in a subprocess, with the repository importable and a deadline."""
    command = where.command(script)
    process = await asyncio.create_subprocess_exec(
        *command,
        # Compose must run from the repository so it finds the compose file;
        # a local run stays in the scratch directory beside the script.
        cwd=str(root if where.kind == "compose" else script.parent),
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(root),
            "AUGURY_CASE_REPO": str(root),
            "HOME": str(Path.home()),
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        # Awaited, so the killed child is reaped rather than left a zombie.
        await process.wait()
        return None, "", ""
    return process.returncode, out.decode(errors="replace"), err.decode(errors="replace")


def _last_number(stdout: str) -> float | None:
    """The measurement is the last number printed, and only that.

    Scanning the whole output would let a script's own logging supply the
    answer, which is how an experiment comes to measure its own constants.
    """
    for line in reversed(stdout.splitlines()):
        found = _NUMBER.findall(line.strip())
        if found:
            return float(found[-1])
    return None


def _tail(text: str, lines: int = 3) -> str:
    return " / ".join(text.strip().splitlines()[-lines:])
