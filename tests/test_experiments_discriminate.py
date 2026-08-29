"""An experiment that cannot fail on correct code is not measuring anything.

This is the highest-value test in the repository, and it exists because three
of the five shipped experiments failed it and their numbers were published:

- `worker_saturation` reported 1.000 for a client with a good timeout, because
  its deadline was under httpx's own default.
- `retry_amplification` reported 3 for a client with backoff, jitter and a
  budget, because one request only ever measures MAX_ATTEMPTS.
- `queries_per_request` reported 51 for a fixed list endpoint, because the
  experiment looped over its own query rather than calling the endpoint.

Each case ships the remediated version of every file it broke. Every experiment
is run against the seeded repository and against the remediated one, and must
report a different number. Without this, a hit rate says nothing about the code.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from augury.evaluation.cases import Case, load_cases

CASES = [case for case in load_cases() if (case.repo.parent / "experiments").is_dir()]


def experiments(case_root: Path) -> list[Path]:
    return sorted((case_root / "experiments").glob("*.py"))


def run(script: Path, repo: Path) -> float | None:
    """The last number the experiment printed, or None if it could not run."""
    result = subprocess.run(
        [sys.executable, str(script)],
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


def remediated(case_root: Path, tmp_path: Path) -> Path:
    """A copy of the repository with every seeded defect fixed."""
    repo = tmp_path / "repo"
    shutil.copytree(case_root / "repo", repo)
    for fixed in (case_root / "fixed").rglob("*.py"):
        target = repo / fixed.relative_to(case_root / "fixed")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixed, target)
    return repo


@pytest.mark.parametrize(
    ("case", "script"),
    [(case, script) for case in CASES for script in experiments(case.repo.parent)],
    ids=lambda value: value.stem if isinstance(value, Path) else value.id,
)
def test_an_experiment_reports_a_different_number_on_remediated_code(
    case: Case, script: Path, tmp_path: Path
) -> None:
    if not (case.repo.parent / "fixed").is_dir():
        pytest.skip(f"{case.id} ships no remediated version")

    seeded = run(script, case.repo)
    fixed = run(script, remediated(case.repo.parent, tmp_path))

    assert seeded is not None, f"{script.name} could not run against the seeded repository"
    assert seeded != fixed, (
        f"{script.name} reports {seeded} whether the defect is present or not, "
        "so no verdict from it says anything about the code"
    )


@pytest.mark.parametrize(
    ("case", "script"),
    [(case, script) for case in CASES for script in experiments(case.repo.parent)],
    ids=lambda value: value.stem if isinstance(value, Path) else value.id,
)
def test_an_experiment_gives_the_same_answer_twice(case: Case, script: Path) -> None:
    """`assert seeded != fixed` on two noisy floats proves nothing: two draws
    from two overlapping distributions differ with probability near one.

    `retry_amplification` reported anywhere from 1.9 to 2.5 for identical code,
    because the socket backlog dropped connections under the burst. The
    documented guarantee that these numbers reproduce exactly is only worth
    making if something checks it.
    """
    first = run(script, case.repo)
    second = run(script, case.repo)

    assert first == second, (
        f"{script.name} reported {first} then {second} for identical code, so a "
        "verdict from it is partly a draw rather than a measurement"
    )


# Every case, not only the ones shipping experiments. The old filter excluded a
# case with no experiments directory from this check entirely, which is how
# A04's single unmeasurable defect went unremarked: the exemption was a
# property of the directory layout rather than a decision anyone wrote down.
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.id)
def test_every_seeded_defect_is_settled_or_says_why_not(case: Case) -> None:
    """A defect whose metric has no experiment can never be proved, and its
    predictions are permanently untested.

    That is allowed, and it has to be declared. `unmeasurable_because` makes
    the omission a sentence someone had to write rather than a gap a reader has
    to notice.
    """
    available = {script.stem for script in experiments(case.repo.parent)}

    for defect in case.defects:
        if defect.expected_metric in available:
            continue
        assert len(defect.unmeasurable_because.split()) >= 8, (
            f"{case.id}/{defect.id} expects {defect.expected_metric}, which no experiment "
            "measures, and gives no reason. Add an experiment, or state in "
            "`unmeasurable_because` why one cannot exist."
        )
