"""Review a case, or evaluate both arms over the case set.

Every published number comes from these commands. They are written to work from
a clean clone and to fail by saying what to do next, because the first thing a
judge does is run one of them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from augury.agents.augury import AuguryReviewer
from augury.agents.baseline import BaselineReviewer
from augury.core.adapters.provider import build_model
from augury.core.cartography import Cartographer
from augury.core.findings import Report
from augury.core.scoring import Score
from augury.core.settings import Settings, SettingsError, load_settings
from augury.evaluation.cases import Case, load_cases
from augury.evaluation.runner import run_arm
from augury.evaluation.sweep import SweepResult, summarise

ARMS = {"baseline": BaselineReviewer, "augury": AuguryReviewer}

# Typer prints local variables in tracebacks by default, and `api_key` is a
# local at every call site that builds a model.
app = typer.Typer(
    help="Reads the code, makes a falsifiable claim, runs the experiment.",
    pretty_exceptions_show_locals=False,
    no_args_is_help=True,
)
console = Console()


@app.command()
def cases() -> None:
    """List the evaluation cases and what each one seeds."""
    table = Table("case", "defects", "description")
    for case in load_cases():
        table.add_row(case.id, str(len(case.defects)), case.repo_description or case.name)
    console.print(table)


@app.command()
def review(
    case: str = typer.Option(..., help="Case id, e.g. B01"),
    arm: str = typer.Option("augury", help="baseline or augury"),
    prove: bool = typer.Option(False, help="Run the case's experiments against the claims"),
) -> None:
    """Review one case with one arm and print what it found."""
    chosen = _case(case)
    reviewer = _arm(arm)
    settings = _settings()

    model = build_model(settings.spec, api_key=settings.api_key)

    async def run() -> Report:
        result: Report = await reviewer(model).review(Cartographer(chosen.repo).map(), chosen.repo)
        return result

    report = asyncio.run(run())
    if prove:
        # Without this the flag was accepted and ignored, so every verdict
        # printed "untested" while the command reported success.
        report = asyncio.run(_prove(chosen, report))
    _print_findings(report)


@app.command()
def evaluate(
    seeds: int = typer.Option(3, min=1, help="How many times to run each arm"),
    prove: bool = typer.Option(False, help="Run the case's experiments against the claims"),
    case: str = typer.Option("", help="Restrict to one case id"),
) -> None:
    """Run every arm over the case set and print the comparison."""
    selected = [c for c in load_cases() if not case or c.id == case]
    if not selected:
        _fail(f"no case matching {case!r}. Available: {_known_cases()}")

    settings = _settings()
    results: dict[str, SweepResult] = {}

    for name, reviewer in ARMS.items():
        scores: list[Score] = []
        for seed in range(seeds):
            scores.extend(asyncio.run(_one_run(name, reviewer, selected, seed, prove, settings)))
        results[name] = summarise(scores)

    _print_comparison(results)


async def _prove(case: Case, report: Report) -> Report:
    """Put every applicable claim to the case's own experiments."""
    from augury.evaluation.runner import measure

    return await measure(case, report)


async def _one_run(
    arm: str,
    reviewer: type[BaselineReviewer] | type[AuguryReviewer],
    cases: list[Case],
    seed: int,
    prove: bool,
    settings: Settings,
) -> list[Score]:
    """One arm, one seed, over every selected case.

    A function rather than a closure in the loop, because a closure would
    capture the loop variables by reference and every seed would run the last
    arm.
    """
    model = build_model(settings.spec, api_key=settings.api_key)

    async def review_one(case: Case) -> Report:
        result: Report = await reviewer(model).review(Cartographer(case.repo).map(), case.repo)
        return result

    return await run_arm(arm, model, cases, seed=seed, reviewer=review_one, prove=prove)


# -- helpers ---------------------------------------------------------------


def _settings() -> Settings:
    try:
        return load_settings()
    except SettingsError as error:
        _fail(str(error))


def _case(identifier: str) -> Case:
    for candidate in load_cases():
        if candidate.id == identifier:
            return candidate
    _fail(f"no case {identifier!r}. Available: {_known_cases()}")


def _arm(name: str) -> type[BaselineReviewer] | type[AuguryReviewer]:
    if name not in ARMS:
        _fail(f"no arm {name!r}. Available: {', '.join(sorted(ARMS))}")
    return ARMS[name]


def _known_cases() -> str:
    return ", ".join(case.id for case in load_cases()) or "none"


def _fail(message: str) -> NoReturn:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _print_findings(report: Report) -> None:
    table = Table("severity", "location", "claim", "verdict")
    for finding in report.findings:
        prediction = finding.prediction
        claim = (
            f"{prediction.metric} {prediction.comparator.value} "
            f"{prediction.value:g}{prediction.unit} @ {prediction.condition}"
            if prediction
            else "[dim]no prediction[/dim]"
        )
        table.add_row(
            finding.severity.value,
            f"{finding.path}:{finding.line}",
            claim,
            finding.verdict.value if finding.verdict else "[dim]untested[/dim]",
        )
    console.print(table)

    for dropped in report.dropped:
        console.print(f"[dim]dropped {dropped.symbol}: {dropped.reason}[/dim]")

    console.print(f"\n{len(report.findings)} findings, ${report.usd:.5f}, {report.seconds:.1f}s")


def _print_comparison(results: dict[str, SweepResult]) -> None:
    table = Table("metric", *results)
    rows: dict[str, Callable[[SweepResult], str]] = {
        "seeded recall (mean)": lambda r: _number(r.recall_mean),
        "  range": lambda r: f"{_number(r.recall_low)}-{_number(r.recall_high)}",
        "falsifiable precision": lambda r: _number(r.precision_mean),
        "hit rate": lambda r: _number(r.hit_rate),
        "  hits / tested": lambda r: f"{r.hits} / {r.tested}",
        "  experiments": lambda r: str(r.experiments),
        "cost usd": lambda r: f"{r.usd_mean:.5f}",
        "seconds": lambda r: f"{r.seconds_mean:.1f}",
    }
    for label, get in rows.items():
        table.add_row(label, *(get(result) for result in results.values()))
    console.print(table)

    if len(results) == 2:
        left, right = results["augury"], results["baseline"]
        verdict = SweepResult.compare(left, right)
        console.print(f"\naugury vs baseline on recall: [bold]{verdict}[/bold]")


def _number(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


if __name__ == "__main__":
    app()
