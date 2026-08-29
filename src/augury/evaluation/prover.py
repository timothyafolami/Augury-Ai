"""Running the experiment that settles a prediction.

The integrity property is that experiments are code shipped with the case,
readable and runnable by anyone, and never something the reviewer supplies. A
reviewer that produced its own measurement would be grading its own homework,
which is precisely the failure the measurement layer exists to prevent.

Everything that can go wrong with running someone else's code -- a missing
experiment, a crash, a hang, output that is not a number -- resolves to Broken
rather than to Miss. Broken says the harness did not answer. Scoring it as a
wrong answer would punish the reviewer for our infrastructure, and would let a
harness that cannot run quietly depress a rival arm.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from augury.core.findings import Measurement
from augury.core.schemas import Prediction
from augury.evaluation.cases import Case

DEFAULT_TIMEOUT = 120.0


class Prover:
    """Runs a case's own experiment for one prediction."""

    def __init__(self, case: Case, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._case = case
        self._timeout = timeout
        self._directory = case.repo.parent / "experiments"

    async def prove(self, prediction: Prediction) -> Measurement:
        """Measure the prediction's metric, or say why it could not be measured."""
        name = f"{self._case.id}/{prediction.metric}"
        script = self._directory / f"{prediction.metric}.py"

        if not script.is_file():
            return Measurement(
                value=None,
                experiment=name,
                detail=f"no experiment for {prediction.metric} in {self._directory}",
            )

        try:
            completed = await asyncio.wait_for(self._run(script), timeout=self._timeout)
        except TimeoutError:
            return Measurement(
                value=None,
                experiment=name,
                detail=f"experiment timed out after {self._timeout:g}s",
            )

        code, stdout, stderr = completed
        if code != 0:
            return Measurement(
                value=None,
                experiment=name,
                detail=f"experiment exited {code}: {stderr.strip()[:200]}",
            )

        value = _last_number(stdout)
        if value is None:
            return Measurement(
                value=None,
                experiment=name,
                detail="experiment printed no number on its last line",
            )

        return Measurement(value=value, experiment=name, detail=stdout.strip()[-200:])

    async def _run(self, script: Path) -> tuple[int, str, str]:
        """Run the experiment in its own process, rooted at the case repository."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            cwd=str(self._case.repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            raise
        return process.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _last_number(stdout: str) -> float | None:
    """The measurement is the last number the experiment printed.

    Experiments log while they work, so the result is what they end with rather
    than the first number that appears in setup output.
    """
    for line in reversed(stdout.strip().splitlines()):
        try:
            return float(line.strip())
        except ValueError:
            continue
    return None
