"""The observation that needed two specialists, made after both have spoken.

Eight specialists read every module and none of them sees the others. That is
deliberate: in a group chat one specialist's wrong claim anchors the next, and
the isolation is what keeps eight opinions independent enough to be worth
having. What it costs is that nobody looks at the whole board, and the most
senior observation about a service is usually the one that needs two readers to
see. A pool sized for one worker count. A timeout longer than the caller's
deadline. A retry with no budget behind a queue with no ceiling. Each half is a
correct, unremarkable finding; together they are the incident.

This is the same honesty problem `core/forecast.py` solved for the risk
forecast, so it is built the same way. An observation is a pydantic model whose
citations are a required field with no default, which means there is no way to
construct one that cannot say which findings it was read off. The specialists
and the derivation are computed from the citations rather than stored beside
them, so a caller who wants a stronger-looking claim has to produce more
findings. And nothing is a synthesis of nothing: an empty result is the correct
output for a healthy report.

The difference is where the grouping comes from. The forecast groups
mechanically, by a rule anybody can reread against the finding it fired on.
This pass asks a model, because the link between a pool size in one file and a
worker count in a compose command is not a phrase match. So the model is given
less rope than usual: it does not receive the source, it cannot introduce a
finding, and it cites by the number the finding was printed under. A number
that is not on the list discards the whole observation rather than the
citation, because an observation half built from something invented is an
observation resting on the invented half.

One rule is not about honesty but about credentials. A finding's path is a
model's output rather than ours, and a specialist can name `.env`. Quoting that
file's name and the sentence written about it back into a prompt would put a
reviewed repository's live keys into a provider request and from there into a
committed cassette, so findings in those files are dropped before the catalogue
is numbered -- which makes them unaddressable rather than merely hidden.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, model_validator

from augury.core.adapters.base import ChatModel
from augury.core.cartography.mapper import holds_live_secrets
from augury.core.drafts import why_it_failed
from augury.core.findings import Finding, Report
from augury.core.scheduling import Coverage
from augury.core.survey.model import Survey
from augury.core.trajectory import Trajectory, redact
from augury.prompts import render

# What makes an observation more than a finding restated. Two, and from two
# different specialists: one specialist reporting twice is something it could
# already say on its own, and the report already says it.
ENOUGH_TO_CONNECT = 2

# How many survive. Past a handful this stops being a senior read of the board
# and becomes a second findings table, which is the artefact it exists to
# avoid. The ones that fall below are recorded rather than silently dropped.
MOST_OBSERVATIONS = 5

# What Observation accepts, less the room the marker needs. A draft declares no
# length limit, so a model writes to the limit it was given, and it was given
# none. Learned the expensive way in `core/drafts.py`, where an unguarded build
# raised after the whole budget was spent.
MAX_TEXT = 4000
_CUT = " [truncated]"


class Citation(BaseModel):
    """One finding, named precisely enough to open.

    The layer travels with it because it is the field the connection rule turns
    on: two citations are a connection only when two specialists reported them,
    and a reader auditing that has to be able to see who said what without
    going back to the report.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    line: int = Field(ge=0)
    symbol: str = Field(min_length=1, max_length=512)
    layer: str = Field(min_length=1, max_length=64)

    @property
    def site(self) -> tuple[str, int, str, str]:
        """Which finding this is. Two citations sharing one are one finding."""
        return (self.path, self.line, self.symbol, self.layer)


class Observation(BaseModel):
    """One thing about the service that no single specialist could have said.

    Three fields carry it and all three are required. The mechanism is the link
    itself, named as a thing rather than as a coincidence. The consequence is
    what the link means for the service, which is the part neither finding
    states. The citations are the findings it was built from, and they have no
    default, so an observation that cannot say where it came from cannot be
    constructed at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mechanism: str = Field(
        min_length=1,
        max_length=4096,
        description="What carries the consequence from one finding to the other",
    )
    consequence: str = Field(
        min_length=1, max_length=4096, description="What this means for the service as a whole"
    )
    citations: tuple[Citation, ...] = Field(
        min_length=ENOUGH_TO_CONNECT,
        description="The findings this was read off. Never fewer than two.",
    )

    @model_validator(mode="after")
    def _every_citation_is_a_different_finding(self) -> Observation:
        sites = {citation.site for citation in self.citations}
        if len(sites) != len(self.citations):
            raise ValueError(
                "one finding cited twice is one finding: an observation built "
                "on it is a finding restated, not a connection"
            )
        return self

    @model_validator(mode="after")
    def _two_specialists_at_least(self) -> Observation:
        """The rule the whole pass rests on, enforced by the type.

        Two findings from one specialist are within what that specialist could
        see on its own, so an observation drawn from them claims a vantage
        point nobody needed this pass for. Checked here rather than in the
        caller, because a validator cannot be forgotten by a second caller.
        """
        if len({citation.layer for citation in self.citations}) < ENOUGH_TO_CONNECT:
            raise ValueError(
                f"an observation needs findings from at least {ENOUGH_TO_CONNECT} "
                "different specialists: one specialist reporting twice saw one thing"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def specialists(self) -> tuple[str, ...]:
        """Who had to speak for this to exist. Computed, never asserted."""
        return tuple(sorted({citation.layer for citation in self.citations}))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derivation(self) -> str:
        """How this came about, carried in the payload rather than in a comment.

        In the payload for the same reason the forecast's is: this is the
        sentence that has to survive the trip to an interface, where a
        paragraph about a service under a confident heading looks exactly like
        a measurement unless something travelling with it says otherwise.
        """
        return (
            f"Read off {len(self.citations)} findings reported by the "
            f"{_listed(self.specialists)} specialists. The connection is stated by "
            "the findings cited above and by nothing else: it was not measured, "
            "no experiment in this repository settles it, and no source was read "
            "to produce it."
        )


class DraftObservation(BaseModel):
    """An observation as the model states it, before anything is believed.

    Findings are cited by the number they were printed under rather than by
    path and line. A path is a string a model can produce from nothing; a
    number either indexes a finding that exists or it does not, and the second
    case is a refusal rather than a plausible-looking citation.
    """

    model_config = ConfigDict(extra="ignore")

    mechanism: str
    consequence: str
    findings: list[int]


class DraftSynthesis(BaseModel):
    """One synthesis pass, as the model states it. Empty is a valid answer."""

    model_config = ConfigDict(extra="ignore")

    observations: list[DraftObservation]


@dataclass(frozen=True)
class Refusal:
    """An observation that was not built, and why it was not.

    Kept rather than discarded because a pass that deletes its own output is
    one nobody can audit, and because the refusals are the evidence that the
    empty results elsewhere are real refusals rather than a broken prompt.
    """

    said: str
    why: str


def citable(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    """The findings this pass may look at, in the order they were ranked.

    Everything except the ones whose file holds live credentials. Those are
    dropped here, before the catalogue is numbered, so a refused finding is not
    merely absent from the prompt but has no number to be cited by.
    """
    return tuple(finding for finding in findings if not _is_a_secret_file(finding.path))


def catalogue(findings: Sequence[Finding]) -> str:
    """The findings as a numbered list, which is also the citation vocabulary.

    Numbered from one because that is how a list is read aloud, and the number
    is what the model answers in. Each line carries the specialist, because the
    rule the model is being asked to satisfy is about which specialists spoke.
    """
    return "\n".join(
        f"{position}. [{finding.layer}] `{finding.path}:{finding.line}` "
        f"`{finding.symbol}` ({finding.severity.value})\n   {finding.mechanism}"
        for position, finding in enumerate(findings, start=1)
    )


def what_was_read(coverage: Coverage | None) -> str:
    """How much of the repository this is a synthesis of.

    An observation about the service as a whole, drawn from a fifth of it, is
    partly a claim about the four fifths nobody opened. The model cannot weigh
    that unless it is told, and a missing coverage record says so rather than
    defaulting to a number that would read as full.
    """
    if coverage is None:
        return (
            "The coverage of this review was not recorded, so how much of the "
            "repository these findings came from is unknown."
        )
    return (
        f"This review read {len(coverage.analysed)} modules and did not read "
        f"{len(coverage.skipped)}. It stopped because {coverage.stopped_because}. "
        "Nothing below is evidence about a module nobody opened."
    )


def how_it_is_deployed(survey: Survey) -> str:
    """The deployment as the repository declares it.

    This is the half of a two-specialist observation that lives in no source
    file: a pool size is not wrong on its own, it is wrong against a worker
    count, and the worker count is in a compose command.

    Environment variables appear by name and never by value. A compose file
    routinely sets a password inline, and the fact worth having here is which
    knobs exist rather than what they are currently turned to.
    """
    lines: list[str] = []
    for service in survey.services:
        lines.append(f"- **{service.name}**")
        lines.append(f"  - built from: `{service.source_root or '.'}`")
        # Verbatim: a worker's concurrency ceiling lives in this string and
        # nowhere else in the repository.
        lines.append(f"  - command: `{service.command or '(none declared)'}`")
        lines.append(f"  - ports: {', '.join(service.ports) or '(none)'}")
        lines.append(f"  - depends on: {', '.join(service.depends_on) or '(nothing)'}")
        named = ", ".join(sorted(service.environment))
        lines.append(f"  - environment variables set (names only): {named or '(none)'}")
    for backing in survey.backing:
        lines.append(
            f"- **{backing.name}** is a {backing.kind} it did not write (`{backing.image}`)"
        )
    if survey.external:
        lines.append(f"- named but not run here: {', '.join(survey.external)}")
    if not lines:
        return "(no deployment configuration was found in this repository)"
    return "\n".join(lines)


def resolve(draft: DraftObservation, findings: Sequence[Finding]) -> Observation | Refusal:
    """One draft, turned into an observation or into the reason it was not.

    Every failure here is a refusal rather than a repair. Trimming an
    unresolvable citation and keeping the rest would let a model reach an
    observation it could not support by citing one real finding and one
    invention, and the observation would then stand on the invention.
    """
    said = _fits(draft.mechanism or "(nothing stated)", 200)

    numbers = list(dict.fromkeys(draft.findings))
    if len(numbers) != len(draft.findings):
        return Refusal(said=said, why=f"cited {draft.findings}, in which a finding repeats")

    beyond = [number for number in numbers if not 1 <= number <= len(findings)]
    if beyond:
        return Refusal(
            said=said,
            why=(
                f"cited {beyond}, which {'is' if len(beyond) == 1 else 'are'} not on "
                f"the list of {len(findings)} findings it was given"
            ),
        )

    citations = tuple(
        Citation(
            path=findings[number - 1].path,
            line=findings[number - 1].line,
            symbol=findings[number - 1].symbol,
            layer=findings[number - 1].layer,
        )
        for number in numbers
    )
    try:
        return Observation(
            mechanism=_fits(draft.mechanism, MAX_TEXT),
            consequence=_fits(draft.consequence, MAX_TEXT),
            citations=citations,
        )
    except ValidationError as refused:
        # Whatever is wrong with one observation, it must not cost the pass.
        return Refusal(said=said, why=why_it_failed(refused))


class Synthesis:
    """The pass that reads the finished report the way a senior engineer would.

    It runs last, after every specialist has reported, and it is the only agent
    here that is given findings instead of source. That is the point: it is
    looking for what is true of the report rather than for what is true of a
    file, and a file in front of it would invite it to start reviewing again.
    """

    def __init__(self, model: ChatModel, *, trajectory: Trajectory | None = None) -> None:
        self._model = model
        self._trace = trajectory

    async def observe(self, *, report: Report, survey: Survey) -> tuple[Observation, ...]:
        """The senior observations this report supports, strongest first.

        Empty is a correct and common answer. A report whose findings never
        connect is a report whose findings never connect, and saying so costs
        nothing; a synthesis that always finds something is a horoscope.
        """
        findings = citable(report.findings)

        # Two structural refusals, both cheaper than a model call and both
        # unanswerable by one. Fewer than two findings is nothing to connect,
        # and findings from one specialist cannot satisfy a rule about two --
        # whatever the model would have replied, every observation built on it
        # would be refused a moment later. This is the triage lesson: a call
        # whose only honest answer is already known buys a chance to be wrong.
        if len(findings) < ENOUGH_TO_CONNECT:
            return self._nothing(f"{len(findings)} findings, so there is nothing to connect")
        speakers = {finding.layer for finding in findings}
        if len(speakers) < ENOUGH_TO_CONNECT:
            return self._nothing(
                f"every finding came from the {_listed(tuple(sorted(speakers)))} "
                "specialist, and an observation needs two"
            )

        prompt = render(
            "synthesis",
            findings=catalogue(findings),
            coverage=what_was_read(report.coverage),
            deployment=how_it_is_deployed(survey),
            specialists=_listed(tuple(sorted(speakers))),
            most=MOST_OBSERVATIONS,
        )
        completion = await self._model.call(prompt=prompt, schema=DraftSynthesis)
        draft = cast("DraftSynthesis", completion.result)
        if self._trace is not None:
            self._trace.record_call(
                agent="synthesis",
                prompt=prompt,
                response=draft.model_dump(),
                usage=completion.usage,
                retries=completion.retries,
            )

        observations: list[Observation] = []
        for item in draft.observations:
            outcome = resolve(item, findings)
            if isinstance(outcome, Refusal):
                # `said` is the model's own prose quoted back. A model call is
                # redacted on the way into the journal and a plain record is
                # not, so this one redacts itself: trajectories are committed
                # and handed to judges, which is where redaction fails closed.
                self._record(
                    "refused",
                    {"said": redact(outcome.said), "why": outcome.why, "cited": item.findings},
                )
                continue
            observations.append(outcome)

        observations.sort(key=_order)
        if len(observations) > MOST_OBSERVATIONS:
            self._record(
                "set aside",
                {
                    "kept": MOST_OBSERVATIONS,
                    "set_aside": len(observations) - MOST_OBSERVATIONS,
                    "why": (
                        "past a handful this is a second findings table rather "
                        "than a senior reading of the first one"
                    ),
                },
            )
        return tuple(observations[:MOST_OBSERVATIONS])

    def _nothing(self, why: str) -> tuple[Observation, ...]:
        """Return no observations, on the record, without paying for a call."""
        self._record("skipped", {"why": why})
        return ()

    def _record(self, action: str, detail: dict[str, object]) -> None:
        if self._trace is not None:
            self._trace.record(agent="synthesis", action=action, detail=detail)


def _is_a_secret_file(path: str) -> bool:
    """Whether a finding's file holds live credentials for the repository.

    The path arrives from a model, so it is split rather than trusted whole:
    `backend/.env` and `.env` are the same refusal, and the shared rule that
    decides is the cartographer's, so the two readers cannot drift apart.
    """
    return holds_live_secrets(path.rsplit("/", 1)[-1])


def _order(observation: Observation) -> tuple[int, int, str]:
    """Most specialists first, then most findings, then the name.

    Three specialists converging is a wider view of the board than two, and
    width is the only thing this pass has that a single specialist did not. The
    mechanism breaks the remaining ties so two runs over one report produce the
    same order and stay comparable.
    """
    return (-len(observation.specialists), -len(observation.citations), observation.mechanism)


def _listed(items: tuple[str, ...]) -> str:
    """Names in a sentence somebody could read aloud without stumbling."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _fits(text: str, limit: int) -> str:
    """The text, short enough to store, saying so when it was shortened.

    Silently cutting a mechanism would publish half a sentence as though this
    pass had written it that way.
    """
    if len(text) <= limit:
        return text
    return text[: limit - len(_CUT)] + _CUT
