"""Review a case, or evaluate both arms over the case set.

Every published number comes from these commands. They are written to work from
a clean clone and to fail by saying what to do next, because the first thing a
judge does is run one of them.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from augury.agents.augury import AuguryReviewer
from augury.agents.baseline import BaselineReviewer
from augury.cli import banner
from augury.cli.banner import counted
from augury.cli.quiet import quiet_dependency_noise
from augury.cli.rendering import languages_read, service_table
from augury.core.adapters.base import ChatModel
from augury.core.adapters.provider import model_from
from augury.core.artifacts import read_artifacts
from augury.core.artifacts.checks import deployment_findings
from augury.core.cartography import Cartographer
from augury.core.cartography.languages import EXTENSIONS
from augury.core.findings import Finding, Measurement, Report
from augury.core.journal import Journal, Run
from augury.core.memo import Memo
from augury.core.proving.environment import Environment, choose_environment
from augury.core.reference import Registry, requirements_of
from augury.core.reference.changelog import changelog_notes
from augury.core.reference.staleness import dependency_audit, dependency_findings
from augury.core.report import write_report
from augury.core.scheduling import Budget
from augury.core.schema import read_migrations, schema_findings
from augury.core.scoring import Score
from augury.core.settings import (
    API_KEY_VARIABLES,
    DEFAULT_PROVIDER,
    Settings,
    SettingsError,
    load_settings,
)
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
# Before any command runs: one dependency warning would otherwise print nine
# lines per model call, which on a real repository is several hundred lines of
# traceback about a field this project never declared.
quiet_dependency_noise()

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
    include_tests: bool = typer.Option(False, help="Count the test suite as part of the service"),
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
        repo = Cartographer(
            root, scope=limits, entrypoints=entrypoints, include_tests=include_tests
        ).map()
    except ValueError as exc:
        _fail(str(exc))

    if found.services:
        services = service_table(found.services)
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
        f"\n{counted(len(repo.modules), 'module')}, "
        f"{counted(sum(m.loc for m in repo.modules), 'line')}"
        f"{' — ' + languages_read(languages) if languages else ''}"
    )
    console.print(
        f"{len(reached)} reachable from an entrypoint, "
        f"{len(repo.unreachable)} not, {len(repo.unparsed)} unparsed"
    )
    if repo.unreachable:
        console.print("\n[bold]no request reaches these[/bold] (first 10):")
        for unreached in repo.unreachable[:10]:
            console.print(f"  {unreached}")

    _print_schema(root, limits)
    _print_dependencies(root, limits)


def _print_dependencies(root: Path, limits: tuple[str, ...]) -> None:
    """What the dependency list says, asked of the registry rather than recalled.

    A model asked which version of a library is current answers from its
    training cutoff, confidently. The registry is free, needs no key, and is
    the authority -- and every failure here is silence, because a review has to
    work offline.
    """
    registry = Registry()
    for base in [root / part for part in limits] or [root]:
        pinned = requirements_of(base)
        if not pinned:
            continue
        audit = dependency_audit(pinned, registry)
        findings = audit.findings
        if not findings and audit.complete:
            continue
        plural = "finding" if len(findings) == 1 else "findings"
        console.print(f"\n[bold]dependencies[/bold] — {len(findings)} {plural}")
        # Without this line the count silently depends on network luck: three
        # runs against one repository printed 2, 6 and 5.
        if not audit.complete:
            console.print(f"  [dim]{audit.coverage()}[/dim]")
        for finding in findings:
            console.print(f"  {finding.rule}", markup=False)
            console.print(f"     {finding.detail}", markup=False)
            console.print(f"     fix: {finding.remediation}", markup=False)


def _print_schema(root: Path, limits: tuple[str, ...]) -> None:
    """What the migrations do to tables that already have rows.

    Printed by the free command because it costs nothing: every rule is a fact
    about DDL rather than a judgement, so no model is asked and none is needed.
    """
    roots = [root / part for part in limits] or [root]
    findings = [f for base in roots for f in schema_findings(read_migrations(base))]
    if not findings:
        return

    plural = "finding" if len(findings) == 1 else "findings"
    console.print(f"\n[bold]schema[/bold] — {len(findings)} {plural} in the migrations")
    for finding in findings:
        # markup=False throughout: a rule name in square brackets is Rich
        # markup, and printing it as markup deleted the rule from the output.
        console.print(f"  {finding.rule}  {finding.path}:{finding.line}", markup=False)
        console.print(f"     {finding.detail}", markup=False)
        console.print(f"     fix: {finding.remediation}", markup=False)


@app.command()
def report(
    path: str = typer.Option(..., help="Repository to review"),
    scope: str = typer.Option("", help="Comma-separated directories to limit the review to"),
    budget: float = typer.Option(
        0.0,
        min=0.0,
        help="Ceiling on spend. 0 reads every module worth reading and reports what it cost",
    ),
    cache: bool = typer.Option(
        True,
        help="Reuse findings for files whose content and prompt are unchanged",
    ),
    prove: int = typer.Option(
        0,
        min=0,
        help=(
            "Settle this many top-ranked findings by writing an experiment and "
            "running it. This executes generated code against your repository"
        ),
    ),
    include_tests: bool = typer.Option(
        False, help="Review the test suite too. Its defects are real and they are different"
    ),
    provider: str = typer.Option("", help="groq | openai | anthropic | deepseek"),
    model: str = typer.Option("", help="Model id, e.g. deepseek-v4-flash"),
    api_key: str = typer.Option("", help="Key for this run, instead of the environment"),
    out: str = typer.Option("augury-report.md", help="Where to write the document"),
) -> None:
    """Review a repository and write a document a team can act on.

    A findings table is the wrong artefact above a few dozen modules: nobody
    triages a hundred rows. This writes what the service is, what its
    deployment declares, what its schema and dependencies say, the findings in
    rank order, and how much of the repository was never looked at.
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        _fail(f"--path must be a directory: {root}")

    settings = _settings_from(provider, model, api_key)
    banner.opening(
        console, target=root.name, provider=settings.spec.provider, model=settings.spec.model
    )

    banner.stage(console, 1, 5, "Surveyor", "reading the deployment before the code")
    found = Surveyor(root).survey()
    limits = tuple(part.strip() for part in scope.split(",") if part.strip())
    entrypoints = tuple({e for service in found.services for e in service.entrypoints})
    banner.note(
        console,
        f"{counted(len(found.services), 'service')}, "
        f"{counted(len(found.backing), 'backing service')}, "
        f"{counted(len(entrypoints), 'entrypoint')} declared by their commands",
    )

    banner.stage(console, 2, 5, "Cartographer", "six languages, imports, request path")
    try:
        repo = Cartographer(
            root, scope=limits, entrypoints=entrypoints, include_tests=include_tests
        ).map()
    except ValueError as exc:
        _fail(str(exc))
    reached = len(repo.modules) - len(repo.unreachable)
    banner.note(
        console,
        f"{counted(len(repo.modules), 'module')}, {reached} reachable from an "
        f"entrypoint, {len(repo.unreachable)} not",
    )

    bases = [root / part for part in limits] or [root]
    banner.stage(console, 3, 5, "Schema", "what the migrations do to tables with rows in them")
    inventory = read_artifacts(root)
    deployment = deployment_findings(inventory.artifacts, root=root)
    schema = tuple(f for base in bases for f in schema_findings(read_migrations(base)))
    registry = Registry()
    dependencies = tuple(
        f for base in bases for f in dependency_findings(requirements_of(base), registry)
    )
    banner.note(
        console,
        f"{counted(len(deployment), 'deployment finding')}, "
        f"{counted(len(schema), 'schema finding')}, "
        f"{counted(len(dependencies), 'dependency finding')}, "
        "all deterministic and free",
    )

    ceiling = f"${budget:.2f}" if budget else "no ceiling"
    banner.stage(console, 4, 5, "Specialists", f"eight concerns, {ceiling}")
    built_model = model_from(settings)

    # Recorded before any specialist runs. A run written down on completion is
    # a run that can never admit to having been interrupted.
    journal = _journal_for(root)
    run_id = uuid.uuid4().hex[:12]
    journal.begin(
        Run(
            run_id=run_id,
            model=f"{settings.spec.provider}/{settings.spec.model}",
            scope=scope or "",
            modules=len(repo.modules),
        )
    )

    async def run() -> Report:
        built = AuguryReviewer(
            built_model,
            budget=Budget(usd=budget) if budget else Budget(),
            watching=_watcher(),
            memo=_memo_for(root, enabled=cache, model_id=built_model.model_id),
        )
        result: Report = await built.review(repo, root)
        return result

    try:
        reviewed = asyncio.run(run())
    except Exception as error:  # the provider is the one thing outside our control
        _fail(_provider_failure(error, provider=settings.spec.provider, model=settings.spec.model))

    if prove:
        # Where the experiments can import the code they measure. A repository
        # whose dependencies live in an image cannot be measured beside it.
        where = choose_environment(root=root, scope=limits, survey=found)
        if where.kind == "compose":
            banner.note(console, f"proving inside the {where.service} image, which has the deps")
        elif where.why:
            banner.note(console, f"proving on this machine: {where.why}")
        reviewed = asyncio.run(
            _settle(reviewed, root=root, model=built_model, how_many=prove, environment=where)
        )

    # Where to read about each major gap. Optional and best-effort: search is
    # the first thing to fail offline, and its absence costs the report a
    # section rather than the run.
    reading: dict[str, tuple[str, ...]] = {}
    for finding in dependencies:
        if finding.rule != "dependency-major-versions-behind":
            continue
        package = finding.detail.split("`")[1] if "`" in finding.detail else ""
        pinned = requirements_of(bases[0]).get(package, "")
        facts = registry.facts_for(package)
        if not package or not facts:
            continue
        notes = changelog_notes(package, pinned, facts.latest)
        if notes:
            reading[package] = tuple(note.url for note in notes[:3])

    banner.stage(console, 5, 5, "Report", "five deterministic passes, then the document")
    document = write_report(
        name=root.name,
        survey=found,
        report=reviewed,
        schema=schema,
        dependencies=dependencies,
        deployment=deployment,
        modules=len(repo.modules),
        unreachable=len(repo.unreachable),
        reading=reading,
    )
    destination = Path(out).expanduser()
    destination.write_text(document, encoding="utf-8")
    journal.finish(
        run_id,
        read=len(reviewed.coverage.analysed) if reviewed.coverage else 0,
        findings=len(reviewed.findings),
        usd=reviewed.usd,
        report=str(destination),
    )
    console.print(f"wrote {destination} ({len(document.splitlines())} lines)")


@app.command()
def review(
    case: str = typer.Option("", help="Case id, e.g. B01"),
    path: str = typer.Option("", help="Any repository to review, instead of a case"),
    scope: str = typer.Option("", help="Comma-separated directories to limit the review to"),
    budget: float = typer.Option(
        0.0,
        min=0.0,
        help="Ceiling on spend. 0 reads every module worth reading and reports what it cost",
    ),
    cache: bool = typer.Option(
        True,
        help="Reuse findings for files whose content and prompt are unchanged",
    ),
    include_tests: bool = typer.Option(
        False, help="Review the test suite too. Its defects are real and they are different"
    ),
    provider: str = typer.Option("", help="groq | openai | anthropic | deepseek"),
    model: str = typer.Option("", help="Model id, e.g. deepseek-v4-flash"),
    api_key: str = typer.Option("", help="Key for this run, instead of the environment"),
    arm: str = typer.Option("augury", help="baseline or augury"),
    prove: int = typer.Option(
        0,
        min=0,
        help=(
            "Settle this many findings by experiment. On a case that runs the "
            "experiments it ships; on a repository it writes them, which "
            "executes generated code against your files"
        ),
    ),
    trajectory: str = typer.Option("", help="Write every step to this JSONL file"),
) -> None:
    """Review a case, or any repository, and print what it found."""
    if case and path:
        _fail("Give --case or --path, not both.")
    if not case and not path:
        _fail("Give --case for a seeded fixture, or --path for your own repository.")
    if path:
        _review_repository(path, scope, budget, arm, trajectory, cache, provider, model, api_key)
        return
    chosen = _case(case)
    reviewer = _arm(arm)
    settings = _settings_from(provider, model, api_key)

    built_model = model_from(settings)

    recording = Trajectory(Path(trajectory)) if trajectory else None

    async def run() -> Report:
        built = reviewer(
            built_model,
            experiments=chosen.experiment_conditions(),
            trajectory=recording,
        )
        result: Report = await built.review(Cartographer(chosen.repo).map(), chosen.repo)
        return result

    try:
        report = asyncio.run(run())
    except Exception as error:  # the provider is the one thing outside our control
        _fail(_provider_failure(error, provider=settings.spec.provider, model=settings.spec.model))
    if prove:
        # Without this the flag was accepted and ignored, so every verdict
        # printed "untested" while the command reported success.
        report = asyncio.run(_prove(chosen, report))
    _print_findings(report)


def _settings_from(provider: str, model: str, api_key: str) -> Settings:
    """Settings from the environment, with any flag given here overriding it.

    A flag rather than only an environment variable because someone testing
    this across four projects should not edit a dotenv between each, and
    someone bringing their own model should not have to edit anything at all.
    """
    for name, value in (
        ("AUGURY_PROVIDER", provider),
        ("AUGURY_MODEL", model),
    ):
        if value:
            os.environ[name] = value
    if api_key and provider:
        os.environ[API_KEY_VARIABLES.get(provider, "AUGURY_API_KEY")] = api_key
    elif api_key:
        # No provider named, so set the key for whichever one is configured.
        configured = os.environ.get("AUGURY_PROVIDER", DEFAULT_PROVIDER)
        os.environ[API_KEY_VARIABLES.get(configured, "AUGURY_API_KEY")] = api_key
    return _settings()


def _journal_for(root: Path) -> Journal:
    """Where a repository's run history lives, beside its remembered findings."""
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Journal(home / "augury" / key)


@app.command()
def history(
    path: str = typer.Option(..., help="Repository whose runs to list"),
) -> None:
    """What has been run against this repository, and what was interrupted.

    A cache says which files were read. It cannot say a run started, so a
    review stopped halfway leaves a warm cache and no reason for it.
    """
    root = Path(path).expanduser().resolve()
    entries = _journal_for(root).history()
    if not entries:
        console.print(f"no runs recorded for {root.name}")
        return

    console.print(f"[bold]{root.name}[/bold] — {len(entries)} runs, newest first\n")
    for entry in entries:
        mark = "[yellow]![/yellow]" if entry.interrupted else "[green]ok[/green]"
        console.print(f" {mark} {entry.summary()}", markup=True)
        console.print(f"    [dim]{entry.model} · scope={entry.scope or 'whole repo'}[/dim]")


async def _settle(
    report_in: Report,
    *,
    root: Path,
    model: ChatModel,
    how_many: int,
    environment: Environment | None = None,
) -> Report:
    """Write and run an experiment for the top findings, and record what it measured.

    Only findings carrying a prediction, and only the top few: findings arrive
    ranked, and proving all of them means one generated script each.

    A failure to settle one finding must not cost the review. The experiment is
    the least reliable thing here -- it is generated, then executed -- so
    anything it raises becomes Broken for that finding and nothing else.
    """
    from augury.core.proving import prove_finding
    from augury.core.proving.generator import CannotMeasure, Generator

    generate = Generator(model)
    settled: list[Finding] = []
    remaining = how_many
    # Proving costs a model call per finding, and report.usd was fixed before
    # any of them ran -- so five experiments were paid for and published as
    # $0.00, in a document whose preamble says every number in it is arithmetic.
    before_proving = model.usage

    console.print(
        f"\n[bold]Proving[/bold] up to {how_many} findings. "
        "[dim]This writes an experiment per finding and runs it against your "
        "repository; each script is saved so you can read what executed.[/dim]"
    )

    for finding in report_in.findings:
        if remaining <= 0 or finding.prediction is None:
            settled.append(finding)
            continue
        remaining -= 1
        try:
            proof = await prove_finding(
                finding, root=root, generate=generate, environment=environment
            )
        except CannotMeasure as refusal:
            console.print(f"  declined {finding.symbol}: {refusal}", markup=False, style="dim")
            settled.append(finding)
            continue
        except Exception as error:
            console.print(
                f"  could not settle {finding.symbol}: {error}", markup=False, style="dim"
            )
            settled.append(finding)
            continue

        if proof is None:
            settled.append(finding)
            continue

        measured = Measurement(
            value=proof.measured,
            experiment=proof.script_path,
            detail=proof.detail,
        )
        settled.append(finding.model_copy(update={"measurement": measured}))
        if proof.measured is None:
            # Why, not merely that. "Printed no number" is true and useless.
            console.print(f"  {finding.symbol}: broken — {proof.detail}", markup=False)
        else:
            console.print(
                f"  {finding.symbol}: measured {proof.measured:g} -> {proof.outcome.value}",
                markup=False,
            )

    spent_proving = (model.usage - before_proving).usd
    return report_in.model_copy(
        update={"findings": tuple(settled), "usd": report_in.usd + spent_proving}
    )


def _memo_for(root: Path, *, enabled: bool, model_id: str = "") -> Memo:
    """Where a repository's remembered findings live.

    Under the user's cache directory rather than inside the repository: a
    reviewer that writes into the tree it is reading has changed the thing it
    is reporting on.
    """
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Memo(home / "augury" / key, model_id=model_id, enabled=enabled)


def _review_repository(
    path: str,
    scope: str,
    budget_usd: float,
    arm: str,
    trajectory: str,
    cache: bool = True,
    provider: str = "",
    model: str = "",
    api_key: str = "",
    include_tests: bool = False,
) -> None:
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
        repo = Cartographer(
            root, scope=limits, entrypoints=entrypoints, include_tests=include_tests
        ).map()
    except ValueError as exc:
        _fail(str(exc))

    console.print(
        f"{len(repo.modules)} modules, {len(repo.unreachable)} of them reached by "
        f"no entrypoint. Budget ${budget_usd:.2f}."
    )

    settings = _settings_from(provider, model, api_key)
    built_model = model_from(settings)
    reviewer = _arm(arm)
    recording = Trajectory(Path(trajectory)) if trajectory else None

    async def run() -> Report:
        # The baseline's ceiling is the prompt, not the money: it sends the
        # repository in one call and drops whatever does not fit. Handing it a
        # dollar budget would imply a knob it does not have.
        built = (
            AuguryReviewer(
                built_model,
                budget=Budget(usd=budget_usd) if budget_usd else Budget(),
                trajectory=recording,
                watching=_watcher(),
                memo=_memo_for(root, enabled=cache, model_id=built_model.model_id),
            )
            if reviewer is AuguryReviewer
            else BaselineReviewer(built_model, trajectory=recording)
        )
        result: Report = await built.review(repo, root)
        return result

    try:
        report = asyncio.run(run())
    except Exception as error:  # the provider is the one thing outside our control
        _fail(_provider_failure(error, provider=settings.spec.provider, model=settings.spec.model))
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


# The environment variable each provider reads its key from. A first run that
# fails on authentication should say which one to set, not make the reader go
# looking for it.
_KEY_NAMES = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# Long enough to carry a provider's own message, short enough that it stays a
# paragraph. One provider returned five thousand characters of HTML.
_MOST_OF_A_MESSAGE = 400


def _provider_failure(error: Exception, *, provider: str, model: str) -> str:
    """One paragraph saying which provider refused, and what to do about it.

    The alternative, and what happened on the first DeepSeek run, is sixty
    lines of traceback through httpx, openai and pydantic -- with everything
    the reader needed on the last line, under frames from libraries they never
    called.
    """
    said = str(error)
    if len(said) > _MOST_OF_A_MESSAGE:
        said = said[:_MOST_OF_A_MESSAGE] + "…"

    key = _KEY_NAMES.get(provider, f"{provider.upper()}_API_KEY")
    lowered = said.lower()

    # Advice only where the cause is known. Naming the key for a failure that
    # was not about the key sends the reader to check the one thing that was
    # already right, which is worse than saying nothing -- and it printed
    # "set DEEPSEEK_API_KEY in .env" for a key that worked.
    advice = ""
    if "401" in said or "403" in said or "authentication" in lowered:
        advice = f"{key} is missing or not accepted — check it in .env"
    elif "429" in said or "rate limit" in lowered:
        advice = "the rate limit was hit and the waits ran out; retry, or use a smaller --scope"
    elif "output limit" in lowered or "max_tokens" in lowered:
        advice = "raise AUGURY_MAX_TOKENS, or narrow --scope so each answer is shorter"
    elif "404" in said or ("model" in lowered and "not" in lowered):
        advice = f"the provider may not recognise {model!r} — check AUGURY_MODEL"

    tail = f"\n{advice}" if advice else ""
    return f"{provider} refused the request for {model}: {said}{tail}"


def _fail(message: str) -> NoReturn:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


# A review of a real repository returns more findings than anyone reads in one
# sitting. They arrive ordered by evidence, so showing the head of the list is
# showing the part worth reading first; the rest is in the trajectory.
SHOWN_BY_DEFAULT = 25


def _watcher() -> Callable[[object], None]:
    """Narrate a review while it runs.

    A review of a real backend runs for minutes. Silence for that long is
    indistinguishable from a hang, and it hides the thing worth watching:
    which module is being read, how far it is from a request, and what the
    budget has actually bought so far.
    """

    def watch(progress: object) -> None:
        found = progress.findings  # type: ignore[attr-defined]
        depth = progress.depth  # type: ignore[attr-defined]
        where = "unreached" if depth is None else f"depth {depth}"
        mark = f"[bold]{found} found[/bold]" if found else "[dim]clean[/dim]"
        console.print(
            f"[dim]{progress.read:>4}/{progress.total}[/dim] "  # type: ignore[attr-defined]
            f"[dim]${progress.usd:6.4f}[/dim]  "  # type: ignore[attr-defined]
            f"{where:<10} {progress.path}  {mark}"  # type: ignore[attr-defined]
        )

    return watch


def _print_findings(report: Report, *, limit: int = SHOWN_BY_DEFAULT) -> None:
    table = Table("#", "severity", "location", "claim", "verdict")
    for position, finding in enumerate(report.findings[:limit], start=1):
        prediction = finding.prediction
        claim = (
            f"{prediction.metric} {prediction.comparator.value} "
            f"{prediction.value:g}{prediction.unit} @ {prediction.condition}"
            if prediction
            else "[dim]no prediction[/dim]"
        )
        table.add_row(
            str(position),
            finding.severity.value,
            f"{finding.path}:{finding.line}",
            claim,
            finding.verdict.value if finding.verdict else "[dim]untested[/dim]",
        )
    console.print(table)

    hidden = len(report.findings) - min(limit, len(report.findings))
    if hidden > 0:
        console.print(
            f"[dim]{hidden} further findings, ranked below these. "
            f"--trajectory writes every one.[/dim]"
        )

    for dropped in report.dropped:
        # style= rather than [dim] tags: markup=False keeps a finding's own
        # text from being read as markup, and prints the tags literally.
        console.print(f"withdrawn {dropped.symbol}: {dropped.reason}", markup=False, style="dim")

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
