"""Proving a forecast instead of publishing it.

A finding says `worker_saturation at_least 0.9x at stripe_latency=2s`. That is
falsifiable, which is not the same as settled: the seeded cases ship
hand-written experiments, and a real repository ships none.

So the experiment is generated, run, and graded. Every part of that is
dangerous in a different way, and the tests here are mostly about the danger:
generated code executes, so it runs in a subprocess with a timeout and its
source is written down first; and a script that fails must produce Broken
rather than a number, because a plausible number from a broken experiment is
the one failure this project has made four times.

No test here runs a model or executes generated code it did not write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.findings import Finding, Severity
from augury.core.proving import Experiment, Proof, prove_finding
from augury.core.schemas import Comparator, Outcome, Prediction

PREDICTION = Prediction(
    metric="queries_per_request",
    comparator=Comparator.AT_LEAST,
    value=40,
    unit="queries",
    condition="50 rows",
)


def _finding() -> Finding:
    return Finding(
        path="app/api.py",
        line=1,
        layer="data",
        symbol="list_orders",
        mechanism="A query per row.",
        severity=Severity.HIGH,
        remediation="Join it.",
        prediction=PREDICTION,
    )


def _writes(number: str) -> str:
    return f"print('measuring')\nprint({number})\n"


async def _prove(tmp_path: Path, script: str, timeout: float = 30.0) -> Proof:
    async def generate(finding: Finding, root: Path) -> Experiment:
        return Experiment(source=script, explanation="counts queries")

    proof = await prove_finding(_finding(), root=tmp_path, generate=generate, timeout=timeout)
    assert proof is not None
    return proof


@pytest.mark.asyncio
async def test_a_measurement_above_the_threshold_is_a_hit(tmp_path: Path) -> None:
    proof = await _prove(tmp_path, _writes("51"))

    assert proof.measured == 51.0
    assert proof.outcome is Outcome.HIT


@pytest.mark.asyncio
async def test_a_measurement_below_the_threshold_is_a_miss(tmp_path: Path) -> None:
    """The forecast was wrong, and saying so is the whole point."""
    proof = await _prove(tmp_path, _writes("2"))

    assert proof.outcome is Outcome.MISS


@pytest.mark.asyncio
async def test_a_script_that_crashes_is_broken_not_a_number(tmp_path: Path) -> None:
    proof = await _prove(tmp_path, "raise SystemExit(3)\n")

    assert proof.measured is None
    assert proof.outcome is Outcome.BROKEN
    assert proof.detail


@pytest.mark.asyncio
async def test_a_script_that_prints_no_number_is_broken(tmp_path: Path) -> None:
    """Silence is not zero."""
    proof = await _prove(tmp_path, "print('I did some work')\n")

    assert proof.outcome is Outcome.BROKEN


@pytest.mark.asyncio
async def test_a_script_that_hangs_is_stopped_and_broken(tmp_path: Path) -> None:
    proof = await _prove(tmp_path, "import time\ntime.sleep(30)\n", timeout=0.5)

    assert proof.outcome is Outcome.BROKEN
    assert "timed out" in proof.detail.lower()


@pytest.mark.asyncio
async def test_the_generated_source_is_written_down_before_it_runs(
    tmp_path: Path,
) -> None:
    """Executing generated code without recording it is unauditable.

    Whatever the verdict, someone has to be able to read what actually ran.
    """
    proof = await _prove(tmp_path, _writes("51"))

    assert proof.script_path
    saved = Path(proof.script_path)
    assert saved.is_file()
    assert "print" in saved.read_text()


@pytest.mark.asyncio
async def test_a_finding_with_no_prediction_is_not_proved(tmp_path: Path) -> None:
    """There is nothing to measure, so nothing is run."""
    ran = False

    async def generate(finding: Finding, root: Path) -> Experiment:
        nonlocal ran
        ran = True
        return Experiment(source="print(1)", explanation="")

    unprovable = _finding().model_copy(update={"prediction": None})
    proof = await prove_finding(unprovable, root=tmp_path, generate=generate)

    assert proof is None
    assert ran is False
