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
from pathlib import Path
from typing import cast

from augury.agents.triage import Triage
from augury.core.adapters.base import ChatModel
from augury.core.cartography import ModuleNode, RepoMap
from augury.core.cartography.languages import EXTENSIONS
from augury.core.cartography.symbols import locator_for
from augury.core.drafts import DraftReport, to_report
from augury.core.findings import Report
from augury.core.layers import Layer
from augury.core.metrics import describe, vocabulary
from augury.core.scheduling import Budget, Scheduler
from augury.core.trajectory import Trajectory
from augury.evaluation.reconcile import reconcile
from augury.prompts import render

# One file is read once per specialist, so a very long file is trimmed rather
# than allowed to dominate the budget it shares with every other module.
MAX_SOURCE_CHARS = 40_000

# Triage, plus the specialists it typically selects. Used only to forecast a
# read before paying for it; actual spend is always measured.
TYPICAL_CALLS_PER_MODULE = 3


class AuguryReviewer:
    """Reviews a repository by choosing what to read and who should read it."""

    def __init__(
        self,
        model: ChatModel,
        *,
        budget: Budget | None = None,
        trajectory: Trajectory | None = None,
        experiments: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._trace = trajectory
        self._experiments = experiments or {}
        self._triage = Triage(model, trajectory=trajectory)
        # One triage call plus a specialist call each. Declared so the budget
        # is a ceiling on what this arm actually spends, not on a fiction.
        self._budget = budget or Budget(calls_per_module=TYPICAL_CALLS_PER_MODULE)

    async def review(self, repo: RepoMap, root: Path) -> Report:
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

        while (module := plan.next()) is not None:
            self._record(
                "scheduler",
                "selected",
                {
                    "path": module.path,
                    "fan_in": module.fan_in,
                    "signals": sorted(s.value for s in module.signals),
                },
            )
            before = self._model.usage
            findings = await self._review_module(module, root, context)
            drafts.append(findings)
            plan.record(
                module,
                findings=len(findings.findings),
                spent_usd=(self._model.usage - before).usd,
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
        return report.model_copy(update={"coverage": plan.coverage})

    async def _review_module(self, module: ModuleNode, root: Path, context: str) -> DraftReport:
        source = self._read(root / module.path)
        language = EXTENSIONS[Path(module.path).suffix.lower()].value

        chosen = await self._triage.route(module, source, language, context)
        if not chosen:
            return DraftReport(findings=[])

        # Specialists are independent by construction: each reads for its own
        # concern only. Running them concurrently costs the same and takes the
        # time of the slowest rather than the sum.
        results = await asyncio.gather(
            *(self._ask(layer, module, source, language, context) for layer in chosen)
        )
        # Specialists collide: pool exhaustion is a network, a data and a
        # failure concern at once, and each will raise it honestly.
        return reconcile(DraftReport(findings=[f for result in results for f in result.findings]))

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
            corpus=layer.brief,
            path=module.path,
            language=language,
            fan_in=module.fan_in,
            source=source,
            context=context,
            metrics=vocabulary(),
            experiments=describe(self._experiments),
        )
        completion = await self._model.call(prompt=prompt, schema=DraftReport)
        if self._trace is not None:
            self._trace.record_call(
                agent=f"analyst:{layer.name}",
                prompt=prompt,
                response=completion.result.model_dump(),
                usage=completion.usage,
                retries=completion.retries,
            )
        return cast("DraftReport", completion.result)

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
