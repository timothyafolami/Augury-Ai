"""Review a case, or evaluate both arms over the case set.

Every published number comes from these commands. They are written to work from
a clean clone and to fail by saying what to do next, because the first thing a
judge does is run one of them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from augury.agents.augury import AuguryReviewer
from augury.agents.baseline import BaselineReviewer
from augury.core.adapters.provider import model_from
from augury.core.cartography import Cartographer
from augury.core.cartography.languages import EXTENSIONS
from augury.core.findings import Report
from augury.core.scheduling import Budget
from augury.core.scoring import Score
from augury.core.settings import Settings, SettingsError, load_settings
from augury.core.survey import Surveyor
from augury.core.trajectory import Trajectory
from augury.evaluation.cases import Case, load_cases
from augury.evaluation.runner import run_arm
from augury.evaluation.significance import verdict
from augury.evaluation.sweep import (
    SweepResult,
    hit_rate_fisher_p,
    recall_permutation_p,
    summarise,
)

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
def survey(
    path: str = typer.Option(..., help="Repository to survey"),
    scope: str = typer.Option("", help="Comma-separated directories to limit the map to"),
) -> None:
    """Read a repository's deployment and structure. Free, and needs no key.

    Everything here is deterministic: the compose file is a declaration, the
    import graph is arithmetic. Run it before paying for a review, because it
    is what tells you which directory is the service, what each one runs, and
    how much of the repository a request can actually reach.
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        _fail(f"--path must be a directory: {root}")

    found = Surveyor(root).survey()
    limits = tuple(part.strip() for part in scope.split(",") if part.strip())
    entrypoints = tuple({e for service in found.services for e in service.entrypoints})

    try:
        repo = Cartographer(root, scope=limits, entrypoints=entrypoints).map()
    except ValueError as exc:
        _fail(str(exc))

    if found.services:
        services = Table("service", "built from", "ports", "command")
        for service in found.services:
            services.add_row(
                service.name,
                service.source_root or ".",
                ", ".join(service.ports) or "-",
                (service.command[:70] or "-"),
            )
        console.print(services)

    if found.backing:
        backing = Table("depends on", "kind", "image")
        for item in found.backing:
            backing.add_row(item.name, item.kind, item.image)
        console.print(backing)

    languages: dict[str, int] = {}
    for module in repo.modules:
        name = EXTENSIONS[Path(module.path).suffix.lower()].value
        languages[name] = languages.get(name, 0) + 1

    reached = [m for m in repo.modules if m.depth is not None]
    console.print(
        f"\n{len(repo.modules)} modules, {sum(m.loc for m in repo.modules):,} lines, "
        f"{dict(sorted(languages.items()))}"
    )
    console.print(
        f"{len(reached)} reachable from an entrypoint, "
        f"{len(repo.unreachable)} not, {len(repo.unparsed)} unparsed"
    )
    if repo.unreachable:
        console.print("\n[bold]no request reaches these[/bold] (first 10):")
        for unreached in repo.unreachable[:10]:
            console.print(f"  {unreached}")


@app.command()
def review(
    case: str = typer.Option("", help="Case id, e.g. B01"),
    path: str = typer.Option("", help="Any repository to review, instead of a case"),
    scope: str = typer.Option("", help="Comma-separated directories to limit the review to"),
    budget: float = typer.Option(0.25, min=0.0, help="Ceiling on what this review may spend"),
    arm: str = typer.Option("augury", help="baseline or augury"),
    prove: bool = typer.Option(False, help="Run the case's experiments against the claims"),
    trajectory: str = typer.Option("", help="Write every step to this JSONL file"),
) -> None:
    """Review a case, or any repository, and print what it found."""
    if case and path:
        _fail("Give --case or --path, not both.")
    if not case and not path:
        _fail("Give --case for a seeded fixture, or --path for your own repository.")
    if path:
        _review_repository(path, scope, budget, arm, trajectory)
        return
    chosen = _case(case)
    reviewer = _arm(arm)
    settings = _settings()

    model = model_from(settings)

    recording = Trajectory(Path(trajectory)) if trajectory else None

    async def run() -> Report:
        built = reviewer(
            model,
            experiments=chosen.experiment_conditions(),
            trajectory=recording,
        )
        result: Report = await built.review(Cartographer(chosen.repo).map(), chosen.repo)
        return result

    report = asyncio.run(run())
    if prove:
        # Without this the flag was accepted and ignored, so every verdict
        # printed "untested" while the command reported success.
        report = asyncio.run(_prove(chosen, report))
    _print_findings(report)


def _review_repository(path: str, scope: str, budget_usd: float, arm: str, trajectory: str) -> None:
    """Review a repository that ships no answer key.

    The survey runs first and for nothing: it says which directories hold
    services and where each one's code starts, and those entrypoints are what
    turn a flat file list into a walk outward along the request path.
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        _fail(f"--path must be a directory: {root}")

    found = Surveyor(root).survey()
    limits = tuple(part.strip() for part in scope.split(",") if part.strip())
    entrypoints = tuple({e for service in found.services for e in service.entrypoints})
    try:
        repo = Cartographer(root, scope=limits, entrypoints=entrypoints).map()
    except ValueError as exc:
        _fail(str(exc))

    console.print(
        f"{len(repo.modules)} modules, {len(repo.unreachable)} of them reached by "
        f"no entrypoint. Budget ${budget_usd:.2f}."
    )

    settings = _settings()
    model = model_from(settings)
    reviewer = _arm(arm)
    recording = Trajectory(Path(trajectory)) if trajectory else None

    async def run() -> Report:
        # The baseline's ceiling is the prompt, not the money: it sends the
        # repository in one call and drops whatever does not fit. Handing it a
        # dollar budget would imply a knob it does not have.
        built = (
            AuguryReviewer(model, budget=Budget(usd=budget_usd), trajectory=recording)
            if reviewer is AuguryReviewer
            else BaselineReviewer(model, trajectory=recording)
        )
        result: Report = await built.review(repo, root)
        return result

    report = asyncio.run(run())
    _print_findings(report)
    if report.coverage is not None:
        console.print(
            f"read {len(report.coverage.analysed)} of {len(repo.modules)} modules, "
            f"stopped because {report.coverage.stopped_because}"
        )


@app.command()
def evaluate(
    seeds: int = typer.Option(
        3,
        min=1,
        help="How many times to repeat each arm. Identical input; only the provider varies",
    ),
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
        # Under replay every repeat is the same recording served again, so the
        # spread between them measures nothing and must not be read as one.
        results[name] = summarise(scores, independent=settings.repeats_are_independent)

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
    model = model_from(settings)

    async def review_one(case: Case) -> Report:
        result: Report = await reviewer(model, experiments=case.experiment_conditions()).review(
            Cartographer(case.repo).map(), case.repo
        )
        return result

    return await run_arm(arm, model, cases, seed=seed, reviewer=review_one, prove=prove)


# -- helpers ---------------------------------------------------------------


@app.command()
def mcp(
    root: str = typer.Option(".", help="The only directory this server will read"),
    max_budget: float = typer.Option(
        1.00, min=0.0, help="Ceiling on what one review may spend, whatever the client asks"
    ),
) -> None:
    """Serve Augury over the Model Context Protocol on stdio.

    The root is fixed here rather than chosen per call: the client driving this
    is a language model, and a model that can name any path can read any file
    on the machine.
    """
    from augury.mcp import Server
    from augury.mcp.server import serve

    boundary = Path(root).expanduser().resolve()
    if not boundary.is_dir():
        _fail(f"--root must be a directory: {boundary}")
    # Mapping and explaining work without a key; only review needs one, and it
    # says so in its own result rather than refusing to start the server.
    try:
        settings = load_settings()
        key: str | None = settings.api_key or None
        replaying = settings.replay_only
    except SettingsError:
        key, replaying = None, False
    serve(
        Server(
            api_key=key,
            allowed_root=boundary,
            max_budget_usd=max_budget,
            # In replay the key is deliberately empty and the run is still able
            # to answer, so a key check alone would refuse the one mode a judge
            # without a key can actually use.
            replaying=replaying,
        )
    )


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
        # Printed because the hit rate cannot be read honestly without it: an
        # untested prediction costs nothing, so an arm graded on fewer of its
        # own claims is graded on its best-aimed ones.
        "  prediction coverage": lambda r: _number(r.coverage_mean),
        "  broken": lambda r: str(r.broken),
        "cost usd": lambda r: f"{r.usd_mean:.5f}",
        "seconds": lambda r: f"{r.seconds_mean:.1f}",
    }
    for label, get in rows.items():
        table.add_row(label, *(get(result) for result in results.values()))
    console.print(table)

    if len(results) == 2:
        _print_significance(results["augury"], results["baseline"])


def _print_significance(left: SweepResult, right: SweepResult) -> None:
    """The verdict, produced by the run rather than argued for afterwards.

    Two claims in this project's changelog were withdrawn after being read off
    a pair of means. Printing the test beside the numbers is what stops a
    third.
    """
    hit = hit_rate_fisher_p(left, right)
    reason = "" if (left.independent and right.independent) else "repeats not independent: "
    console.print(f"\nhit rate  {reason}p = {_probability(hit)}  [bold]{verdict(hit)}[/bold]")
    console.print(f"recall    {_why(left, right)}: [bold]{SweepResult.compare(left, right)}[/bold]")
    # The permutation test the hot take reports. Computed here so no published
    # statistic is one that no shipped command produces.
    recall_p = recall_permutation_p(left, right)
    console.print(f"recall    permutation p = {_probability(recall_p)}")


def _why(left: SweepResult, right: SweepResult) -> str:
    """The reason behind the recall verdict, so the line cannot mislead.

    It printed "ranges overlap" unconditionally, including for replay, where
    the ranges are zero-width and do not overlap and the real reason is that
    the repeats were one recording served five times.
    """
    if not (left.independent and right.independent):
        return "repeats not independent"
    return (
        "ranges overlap" if SweepResult.compare(left, right) == "inconclusive" else "ranges clear"
    )


def _probability(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "n/a"


def _number(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


if __name__ == "__main__":
    app()
