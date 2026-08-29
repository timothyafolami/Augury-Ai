"""Drive one arm over the case set.

Every arm sees identical cases and is scored by identical code. That is what
makes two rows in the results table comparable, so the runner owns both rather
than trusting each arm to be fair to itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from augury.agents.baseline import BaselineReviewer
from augury.core.adapters.base import ChatModel
from augury.core.cartography import Cartographer
from augury.core.findings import Report
from augury.core.scoring import Score, score
from augury.evaluation.cases import Case

Reviewer = Callable[[Case], Awaitable[Report]]


async def run_arm(
    arm: str,
    model: ChatModel,
    cases: list[Case],
    *,
    seed: int = 0,
    reviewer: Reviewer | None = None,
) -> list[Score]:
    """Review every case with one arm and score each result.

    A case that raises is recorded as a failure rather than ending the sweep or
    vanishing from the denominator: one provider hiccup must not cost the whole
    run, and a review that crashed did not find the defect.
    """
    review = reviewer or _baseline_reviewer(model)
    results: list[Score] = []

    for case in cases:
        try:
            report = await review(case)
            failed = False
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            report = Report(model_id=model.model_id, seconds=0.0)
            failed = True
            _note(case, exc)

        results.append(
            score(
                report,
                case=case.id,
                arm=arm,
                seed=seed,
                detected=case.detected_by(report),
                failed=failed,
            )
        )

    return results


def _baseline_reviewer(model: ChatModel) -> Reviewer:
    async def review(case: Case) -> Report:
        return await BaselineReviewer(model).review(Cartographer(case.repo).map(), case.repo)

    return review


def _note(case: Case, exc: Exception) -> None:
    """A failure is reported to the operator and counted against the arm."""
    print(f"  {case.id}: review failed: {type(exc).__name__}: {exc}")
