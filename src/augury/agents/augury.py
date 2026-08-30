"""The pipeline arm: schedule, triage, specialise, refine.

Its claim over a single prompt is not a bigger model. It is that it chooses
what to read under a budget, routes each file only to specialists that can say
something about it, gives each specialist the practice-lab knowledge that
defines its concern, and refuses to publish a claim it cannot make testable.

Everything expensive here is a deliberate purchase, and every purchase is
recorded so the report can be honest about what it bought.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from augury.agents.triage import Triage
from augury.core.adapters.base import ChatModel
from augury.core.cartography import ModuleNode, RepoMap
from augury.core.cartography.languages import EXTENSIONS, Language
from augury.core.cartography.symbols import locator_for
from augury.core.corpus import corpus_for
from augury.core.drafts import DraftReport, to_report
from augury.core.findings import Dropped, Report
from augury.core.indexes import indexed_columns, withdraw_false_index_claims
from augury.core.languages import brief_for
from augury.core.layers import Layer, specialists_for
from augury.core.memo import Memo
from augury.core.metrics import describe, vocabulary
from augury.core.priority import rank
from augury.core.reachability import cap_severity
from augury.core.reference import Registry, requirements_of
from augury.core.repetition import collapse
from augury.core.scheduling import Budget, Scheduler
from augury.core.schema import read_migrations
from augury.core.trajectory import Trajectory
from augury.core.versions import describe_versions
from augury.evaluation.reconcile import reconcile
from augury.prompts import render

# Modules reviewed at once. Full coverage of a real backend is 261 modules and
# one at a time is an hour, which is why the first runs were budget-capped at a
# sixth of the repository -- hiding wall-clock behind a cost ceiling. The cost
# of the whole thing is under two dollars.
DEFAULT_CONCURRENCY = 8


@dataclass(frozen=True)
class Progress:
    """One module finished, for a caller that wants to watch."""

    path: str
    depth: int | None
    findings: int
    read: int
    total: int
    usd: float


# One file is read once per specialist, so a very long file is trimmed rather
# than allowed to dominate the budget it shares with every other module.
MAX_SOURCE_CHARS = 40_000

# What stands in for the lab when it is not on this machine. It says the
# specialist has no corpus, rather than leaving a heading promising one over
# nothing, because a prompt that claims a source it lacks invites a citation
# nobody can check.
NO_CORPUS = (
    "The practice lab is not present on this machine, so you have no corpus "
    "to cite. Reason from the brief above and say plainly when a claim rests "
    "on your own knowledge rather than on material given to you."
)

# Triage, plus the specialists it typically selects. Used only to forecast a
# read before paying for it; actual spend is always measured.
TYPICAL_CALLS_PER_MODULE = 3


@dataclass(frozen=True)
class Reading:
    """What came back from trying to read one module.

    A module whose specialists all failed produces no findings for the same
    reason an unread file produces none: nobody looked. Returning a bare
    DraftReport made the two indistinguishable, so the review reported a module
    as analysed that no specialist had successfully read -- and the worse the
    provider behaved, the cleaner the report looked.
    """

    report: DraftReport
    read: bool = True
    why: str = ""

    @classmethod
    def of(cls, report: DraftReport) -> Reading:
        return cls(report=report)

    @classmethod
    def unread(cls, path: str, why: str) -> Reading:
        return cls(report=DraftReport(findings=[]), read=False, why=why)

    @classmethod
    def nobody_asked(cls, path: str, *, allowed: int) -> Reading:
        """Triage was consulted and narrowed to no specialist.

        Structurally a valid answer, and not a reading: the signals allowed
        specialists and none was asked, so nothing looked at this file. A
        provider whose structured output degrades under load returns this for
        every module, and the run would report full coverage of a repository
        no analyst saw.
        """
        return cls(
            report=DraftReport(findings=[]),
            read=False,
            why=(f"triage narrowed {allowed} allowed specialists to none, so no analyst read it"),
        )


async def gather_survivors(
    work: Sequence[Awaitable[DraftReport]],
    *,
    note: Callable[[Exception], None] | None = None,
) -> list[DraftReport]:
    """Run these concurrently and return the ones that finished.

    A provider fault is the likeliest failure in this system and the least
    interesting: it says nothing about the code under review. Absorbing it
    here costs one opinion about one concern; letting it out costs the run.

    Cancellation is not absorbed -- Ctrl-C has to keep working.
    """
    done = await asyncio.gather(*work, return_exceptions=True)
    kept: list[DraftReport] = []
    for outcome in done:
        if isinstance(outcome, BaseException):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if note is not None and isinstance(outcome, Exception):
                note(outcome)
            continue
        kept.append(outcome)
    return kept


async def gather_each(
    work: Sequence[Awaitable[Reading]],
    *,
    instead: Reading,
    note: Callable[[int, Exception], None] | None = None,
) -> list[Reading]:
    """Run these concurrently, one result per item, in order.

    Unlike gather_survivors this keeps position: the batch's cost is
    apportioned by zipping modules with their results, so dropping a failure
    would charge every later module for the wrong read. A module that could
    not be read comes back as a module with no findings, which is what it is,
    and is counted as read so the scheduler does not offer it again forever.
    """
    done = await asyncio.gather(*work, return_exceptions=True)
    kept: list[Reading] = []
    for index, outcome in enumerate(done):
        if isinstance(outcome, BaseException):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if note is not None and isinstance(outcome, Exception):
                note(index, outcome)
            kept.append(instead)
            continue
        kept.append(outcome)
    return kept


class AuguryReviewer:
    """Reviews a repository by choosing what to read and who should read it."""

    def __init__(
        self,
        model: ChatModel,
        *,
        budget: Budget | None = None,
        trajectory: Trajectory | None = None,
        experiments: dict[str, str] | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
        watching: Callable[[Progress], None] | None = None,
        memo: Memo | None = None,
    ) -> None:
        self._model = model
        self._trace = trajectory
        self._experiments = experiments or {}
        self._triage = Triage(model, trajectory=trajectory)
        # One triage call plus a specialist call each. Declared so the budget
        # is a ceiling on what this arm actually spends, not on a fiction.
        self._budget = budget or Budget(calls_per_module=TYPICAL_CALLS_PER_MODULE)
        # Resolved once per review in `review`, because the registry is asked
        # over the network and a specialist call must not wait on it.
        self._pinned: dict[str, str] = {}
        self._registry = Registry()
        self._concurrency = max(1, concurrency)
        # Called after every module. A review of a real backend runs for
        # minutes; silence for that long is indistinguishable from a hang.
        self._watching = watching
        # Disabled unless a caller supplies one. A cache that turns itself on
        # is a cache that can serve a stale answer to someone who did not ask
        # for one.
        self._memo = memo or Memo(Path("."), enabled=False)

    async def review(self, repo: RepoMap, root: Path) -> Report:
        # What this repository declares it depends on. Read once; the registry
        # answers are cached per package for the life of the review.
        self._pinned = requirements_of(root)

        started = time.monotonic()
        context = _render_context(repo.context)
        opening = self._model.usage
        plan = Scheduler(repo, self._budget)
        drafts: list[DraftReport] = []
        self._record(
            "cartographer",
            "mapped",
            {
                "modules": len(repo.modules),
                "unparsed": len(repo.unparsed),
                "context_files": sorted(repo.context),
            },
        )

        while batch := plan.next_batch(self._concurrency):
            for module in batch:
                self._record(
                    "scheduler",
                    "selected",
                    {
                        "path": module.path,
                        "depth": module.depth,
                        "fan_in": module.fan_in,
                        "signals": sorted(s.value for s in module.signals),
                    },
                )

            before = self._model.usage
            # One batch at a time rather than the whole repository at once: the
            # scheduler promotes a module whose neighbours produced findings,
            # and that adaptivity needs results back before the next choice.
            # A module that cannot be read is a module with no findings, not
            # the end of the review. Position is preserved because the cost of
            # the batch is apportioned by zipping these with `batch`.
            results = await gather_each(
                [self._review_module(module, root, context) for module in batch],
                instead=Reading.unread("", "the module could not be read at all"),
                note=lambda index, error: self._record(
                    "module",
                    "failed",
                    {"path": batch[index].path, "why": str(error)[:200]},
                ),
            )
            batch_usd = (self._model.usage - before).usd

            for module, found in zip(batch, results, strict=True):
                drafts.append(found.report)
                # The batch's cost, apportioned. Per-module attribution would
                # need per-call accounting through the gather, and the
                # scheduler only needs the total to know when to stop.
                plan.record(
                    module,
                    findings=len(found.report.findings),
                    spent_usd=batch_usd / len(batch),
                    read=found.read,
                    why=found.why,
                )
                if self._watching is not None:
                    self._watching(
                        Progress(
                            path=module.path,
                            depth=module.depth,
                            findings=len(found.report.findings),
                            read=len(plan.coverage_analysed),
                            total=len(repo.modules),
                            usd=(self._model.usage - opening).usd,
                        )
                    )

        self._record("scheduler", "stopped", plan.coverage.model_dump())
        spent = self._model.usage - opening
        report = to_report(
            DraftReport(findings=[f for draft in drafts for f in draft.findings]),
            model_id=self._model.model_id,
            usd=spent.usd,
            seconds=time.monotonic() - started,
            # The specialist names the symbol; the parser supplies the line.
            locator=locator_for(root),
        )
        # Two passes over the finished report, both deterministic.
        #
        # Severity is capped by whether a request reaches the code, because the
        # specialist is told "high, medium or low" and nothing else, and on a
        # real service answered "high" 92 times out of 141. Lowered only: it
        # read the source and the import graph did not.
        #
        # Then findings saying one sentence about many files are collapsed. A
        # missing correlation id is a property of a service, and reporting it
        # once per handler put sixteen copies of one observation into a list
        # somebody has to triage.
        depths = {module.path: module.depth for module in repo.modules}
        has_entry = any(module.depth is not None for module in repo.modules)
        anchored = [
            cap_severity(
                finding,
                depth=depths.get(finding.path),
                has_entrypoints=has_entry,
                # Whether the map has this path at all. Without it an
                # unrecognised path -- one the model omitted or spelled
                # differently -- was demoted as if it had been measured.
                known=finding.path in depths,
            )
            for finding in report.findings
        ]

        # A claim the migrations settle is not an open question. Withdrawn
        # rather than silently dropped: the count belongs beside the findings,
        # because a reviewer that quietly deletes its own output is one nobody
        # can audit.
        indexed = indexed_columns(read_migrations(root))
        kept, withdrawn = withdraw_false_index_claims(anchored, indexed)

        fan_in = {module.path: module.fan_in for module in repo.modules}
        # Collapsing returns what it stood in for as well as what survived.
        # A finding in neither list leaves the falsifiable-precision
        # denominator, which counts findings plus discarded, and merging on
        # one arm alone lifted that arm's score with no change to the reviewer.
        surviving, stood_in_for = collapse(kept)
        ordered = rank(surviving, depths=depths, fan_in=fan_in)

        return report.model_copy(
            update={
                "coverage": plan.coverage,
                "findings": tuple(ordered),
                "dropped": report.dropped
                + tuple(
                    Dropped(symbol=w.finding.symbol, path=w.finding.path, reason=w.reason)
                    for w in withdrawn
                )
                + tuple(stood_in_for),
            }
        )

    async def _review_module(self, module: ModuleNode, root: Path, context: str) -> Reading:
        source = self._read(root / module.path)
        language = EXTENSIONS[Path(module.path).suffix.lower()].value

        allowed = specialists_for(module.signals)
        chosen = await self._triage.route(module, source, language, context)
        if not chosen:
            if allowed:
                # The signals allowed specialists and triage picked none. That
                # is the model's answer, not a reading of the file.
                return Reading.nobody_asked(module.path, allowed=len(allowed))
            # No specialist's concern appears in this file at all. That is a
            # reading, and a cheap one: nothing here was worth asking about.
            return Reading.of(DraftReport(findings=[]))

        # Specialists are independent by construction: each reads for its own
        # concern only. Running them concurrently costs the same and takes the
        # time of the slowest rather than the sum.
        # One specialist failing costs its opinion, not the review. A run
        # ended on its eleventh module because a provider returned no content
        # three times: the exception left the gather and took thirty-eight
        # unread modules and every finding already in hand with it.
        results = await gather_survivors(
            [self._ask(layer, module, source, language, context) for layer in chosen],
            note=lambda error: self._record(
                "specialist",
                "failed",
                {"path": module.path, "why": str(error)[:200]},
            ),
        )
        if not results:
            # Every specialist failed. No findings, for the same reason an
            # unread file has none, and the difference has to survive.
            return Reading.unread(
                module.path,
                f"all {len(chosen)} specialists failed, so it was charged but never read",
            )

        # Specialists collide: pool exhaustion is a network, a data and a
        # failure concern at once, and each will raise it honestly.
        merged = reconcile(DraftReport(findings=[f for r in results for f in r.findings]))
        if len(results) < len(chosen):
            return Reading(
                report=merged,
                read=True,
                why=f"{len(chosen) - len(results)} of {len(chosen)} specialists failed",
            )
        return Reading.of(merged)

    def _record(self, agent: str, action: str, detail: dict[str, object]) -> None:
        if self._trace is not None:
            self._trace.record(agent=agent, action=action, detail=detail)

    async def _ask(
        self, layer: Layer, module: ModuleNode, source: str, language: str, context: str
    ) -> DraftReport:
        prompt = render(
            "analyst",
            layer_name=layer.name,
            layer_brief=layer.brief,
            # The lab this layer was written from, not the brief again. When
            # the lab is absent this is empty and the prompt says so rather
            # than claiming a source it was not given.
            corpus=corpus_for(layer.lab_layer) or NO_CORPUS,
            path=module.path,
            language=language,
            # How this concern actually appears in this runtime. The layer
            # brief names the concern; without this the specialist supplies the
            # runtime-specific half itself, differently each time.
            language_brief=brief_for(Language(language)),
            # The installed versions, so a claim about a library's defaults is
            # grounded in what is installed rather than in a training cutoff.
            versions=describe_versions(
                set(module.external), pinned=self._pinned, registry=self._registry
            ),
            fan_in=module.fan_in,
            source=source,
            context=context,
            metrics=vocabulary(),
            experiments=describe(self._experiments),
        )
        # The rendered prompt is the question, so it is the key: a changed
        # layer brief, language brief or version block correctly misses.
        remembered = self._memo.recall(source, layer.name, language, prompt)
        if remembered is not None:
            return remembered

        completion = await self._model.call(prompt=prompt, schema=DraftReport)
        draft = cast("DraftReport", completion.result)
        self._memo.remember(source, layer.name, language, prompt, draft)
        if self._trace is not None:
            self._trace.record_call(
                agent=f"analyst:{layer.name}",
                prompt=prompt,
                response=completion.result.model_dump(),
                usage=completion.usage,
                retries=completion.retries,
            )
        return draft

    @staticmethod
    def _read(path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) <= MAX_SOURCE_CHARS:
            return text
        return text[:MAX_SOURCE_CHARS] + "\n... truncated ...\n"


def _render_context(files: dict[str, str]) -> str:
    """The deployment files, or an honest statement that there are none."""
    if not files:
        return "(no deployment configuration was found in this repository)"
    return "\n\n".join(f"### {name}\n```\n{text}\n```" for name, text in files.items())
