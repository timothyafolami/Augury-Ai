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
from augury.core.findings import Finding, Measurement, Report
from augury.core.scoring import Score, score
from augury.evaluation.cases import Case
from augury.evaluation.prover import Prover, applies_to

Reviewer = Callable[[Case], Awaitable[Report]]


async def run_arm(
    arm: str,
    model: ChatModel,
    cases: list[Case],
    *,
    seed: int = 0,
    reviewer: Reviewer | None = None,
    prove: bool = False,
) -> list[Score]:
    """Review every case with one arm and score each result.

    A case that raises is recorded as a failure rather than ending the sweep or
    vanishing from the denominator: one provider hiccup must not cost the whole
    run, and a review that crashed did not find the defect.

    With `prove`, every falsifiable finding is put to the case's own experiment
    and the measurement attached. Off by default because experiments cost real
    time, and a run that did not ask for them must not silently pay for them.
    """
    if reviewer is None:
        # An omitted keyword once published baseline results under the augury
        # label, and every downstream check verifies arms by that same string,
        # so nothing could detect it.
        raise ValueError("run_arm needs an explicit reviewer: the arm label is only a label")
    review = reviewer
    results: list[Score] = []

    for case in cases:
        try:
            report = await review(case)
            failed = False
        except Exception as exc:  # recorded and counted, never swallowed
            report = Report(model_id=model.model_id, seconds=0.0)
            failed = True
            _note(case, exc)

        if prove and not failed:
            report = await measure(case, report)

        results.append(
            score(
                report,
                case=case.id,
                arm=arm,
                seed=seed,
                seeded=len(case.defects),
                found=len(case.found_by(report)),
                failed=failed,
            )
        )

    return results


def baseline_reviewer(model: ChatModel) -> Reviewer:
    """The default arm, named so a caller must ask for it on purpose."""
    return _baseline_reviewer(model)


def _baseline_reviewer(model: ChatModel) -> Reviewer:
    async def review(case: Case) -> Report:
        reviewer = BaselineReviewer(model, experiments=case.experiment_conditions())
        return await reviewer.review(Cartographer(case.repo).map(), case.repo)

    return review


def _note(case: Case, exc: Exception) -> None:
    """A failure is reported to the operator and counted against the arm."""
    print(f"  {case.id}: review failed: {type(exc).__name__}: {exc}")


async def measure(case: Case, report: Report) -> Report:
    """Put every falsifiable finding to the case's own experiment.

    One experiment per metric, run once and shared: twenty findings about the
    same mechanism get one measurement between them, which is also how the
    score counts them.
    """
    prover = Prover(case)
    measured: dict[str, Measurement] = {}
    findings: list[Finding] = []

    for finding in report.findings:
        if finding.prediction is None:
            findings.append(finding)
            continue

        metric = finding.prediction.metric
        locations = prover.locations_for(metric)
        if not applies_to(finding.prediction, path=finding.path, locations=locations):
            # The experiment measures a defect somewhere else. Settling this
            # claim with it would grade a file the measurement is not about.
            findings.append(finding)
            continue

        if metric not in measured:
            measured[metric] = await prover.prove(finding.prediction)
        findings.append(finding.model_copy(update={"measurement": measured[metric]}))

    return report.model_copy(update={"findings": tuple(findings)})
