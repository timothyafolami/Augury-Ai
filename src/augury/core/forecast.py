"""What is likely to give way, and roughly in what order.

A list of findings answers "what is wrong here". It does not answer the
question an operator actually has, which is "what breaks first". Seventeen
findings scattered across a service hide the fact that five of them are one
resource under pressure from five directions: a pool sized for eight, a worker
count of sixteen, a missing timeout, a retry with no budget, and a session held
open across a network call are not five problems, they are one queue.

So a pressure is grouped by mechanism rather than by file. The mechanisms are
the concerns the layer briefs already name, and the specialist that owns a
concern is the one whose word about it counts, which is the same routing
`layers.py` uses to decide who reviews what.

The number attached to a pressure is a count of findings and nothing else.
There is deliberately no probability here. A percentage would claim a
measurement: to say a pool will exhaust with probability 0.7 you need an
arrival rate, a service time and a distribution, and this tool has none of the
three at review time. Every other number this project publishes was counted or
observed, and the moment a forecast prints 70% a reader stops being able to
tell which kind of number they are looking at. What can be stated honestly is
ordinal: how many independent findings point at the same mechanism, and which
band that count falls in. `derivation` says so on every item, in the payload
rather than in a comment, because the comment does not travel to the interface.

A renderer should draw the bar from `independent_findings`, one segment per
finding, so the length of the bar is a thing somebody can recount. A bar drawn
as a fraction of a full width would be reintroducing the percentage through the
graphics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from augury.core.cartography import Signal
from augury.core.findings import Finding
from augury.core.layers import specialists_for
from augury.core.repetition import SYSTEMIC_FILES

REPEATED_AT = 2
"""Two independent findings are corroboration. One is an observation."""

# Borrowed rather than invented. `repetition` already defends three as the line
# between a coincidence and a property of the service, and a forecast that drew
# that line somewhere else would be two thresholds disagreeing in one report.
SYSTEMIC_AT = SYSTEMIC_FILES


class Band(StrEnum):
    """How much of the review points one way. Ordinal, and only ordinal.

    A band is a position in a sequence, not a magnitude. `SYSTEMIC` does not
    mean three times `ISOLATED`, it means the review reached the same mechanism
    from enough directions that it is a property of the service.
    """

    ISOLATED = "isolated"
    REPEATED = "repeated"
    SYSTEMIC = "systemic"

    @property
    def rung(self) -> int:
        """Position on the scale, for a renderer that needs to sort or step."""
        return _RUNGS[self]

    @classmethod
    def for_count(cls, findings: int) -> Band:
        if findings >= SYSTEMIC_AT:
            return cls.SYSTEMIC
        if findings >= REPEATED_AT:
            return cls.REPEATED
        return cls.ISOLATED


_RUNGS = {Band.ISOLATED: 1, Band.REPEATED: 2, Band.SYSTEMIC: 3}


class Mechanism(StrEnum):
    """What gives way, named by the resource rather than by the file.

    These are the concerns the layer briefs teach a specialist to hunt, stated
    as the thing that fails rather than as the defect that causes it. Two
    findings belong together when an operator would watch the same graph.
    """

    QUERY_AMPLIFICATION = "query amplification"
    DATABASE_CONTENTION = "database contention"
    DUPLICATE_SIDE_EFFECTS = "duplicate side effects"
    RETRY_AMPLIFICATION = "retry amplification"
    QUEUE_SATURATION = "queue saturation"
    SHARED_STATE_CORRUPTION = "shared state corruption"
    POOL_EXHAUSTION = "connection pool exhaustion"
    SILENT_FAILURE = "silent failure"
    SERVICE_COUPLING = "service coupling"
    SECRET_EXPOSURE = "secret exposure"
    UNTRUSTED_INPUT = "untrusted input reaching a sink"
    BROKEN_AUTHORISATION = "broken authorisation"
    BLIND_OPERATION = "undiagnosable failure"


@dataclass(frozen=True)
class Rule:
    """When a finding counts toward a mechanism, in terms somebody can check.

    Two halves, and both are needed. The concern says which specialist's word
    counts, so a security reviewer's aside about a pool does not become
    capacity evidence. The phrases say what the finding had to name, so the
    reader can open the finding and see the rule fire on a word that is there.
    """

    mechanism: Mechanism
    concerns: frozenset[Signal]
    phrases: tuple[str, ...]

    @property
    def specialists(self) -> tuple[str, ...]:
        """The layers whose findings this rule accepts, from the same routing
        table that decided who reviewed the file in the first place."""
        return tuple(layer.name for layer in specialists_for(self.concerns))

    @property
    def statement(self) -> str:
        """The rule as it travels with the pressure, for a reader to audit."""
        return (
            f"a {_listed(self.specialists, 'or')} specialist "
            f"named one of: {', '.join(self.phrases)}"
        )


# Order is resolution order: the first rule that accepts a finding takes it,
# and no finding counts twice. A missing timeout genuinely presses on both the
# pool and the queue, but counting it under both would turn one observation
# into two pressures, which is the inflation this tool exists not to do.
# Within a concern the specific rules come before the general ones.
RULES: tuple[Rule, ...] = (
    Rule(
        mechanism=Mechanism.QUERY_AMPLIFICATION,
        concerns=frozenset({Signal.DATA}),
        phrases=(
            "n+1",
            "query per",
            "queries per",
            "query in a loop",
            "queries in a loop",
            "queries inside",
            "missing index",
            "no index",
            "without an index",
            "unindexed",
            "full table scan",
            "sequential scan",
        ),
    ),
    Rule(
        mechanism=Mechanism.DATABASE_CONTENTION,
        concerns=frozenset({Signal.DATA}),
        phrases=(
            "read-modify-write",
            "for update",
            "lost update",
            "isolation level",
            "read committed",
            "repeatable read",
            "serializable",
            "row lock",
            "held open across",
            "held across",
            "long-running transaction",
        ),
    ),
    Rule(
        mechanism=Mechanism.DUPLICATE_SIDE_EFFECTS,
        concerns=frozenset({Signal.DISTRIBUTED}),
        phrases=(
            "idempoten",
            "redeliver",
            "delivered twice",
            "at-least-once",
            "exactly once",
            "duplicate",
            "check-then-act",
            "fencing token",
            "acknowledge",
        ),
    ),
    Rule(
        mechanism=Mechanism.RETRY_AMPLIFICATION,
        concerns=frozenset({Signal.FAILURE, Signal.DISTRIBUTED}),
        phrases=("retry", "retries", "retried", "backoff", "jitter", "stampede", "thundering herd"),
    ),
    Rule(
        mechanism=Mechanism.QUEUE_SATURATION,
        concerns=frozenset({Signal.FAILURE, Signal.DISTRIBUTED, Signal.CONCURRENCY}),
        phrases=(
            "queue",
            "backpressure",
            "back pressure",
            "shedding",
            "shed load",
            "unbounded buffer",
            "queueing delay",
        ),
    ),
    Rule(
        mechanism=Mechanism.SHARED_STATE_CORRUPTION,
        concerns=frozenset({Signal.CONCURRENCY}),
        phrases=(
            "shared state",
            "shared mutable",
            "race",
            "not atomic",
            "non-atomic",
            "read-modify-write",
            "check-then-act",
            "lock ordering",
            "deadlock",
            "without synchronis",
            "without a lock",
            "the gil",
        ),
    ),
    Rule(
        mechanism=Mechanism.POOL_EXHAUSTION,
        # Four specialists reach this one resource, which is the whole reason a
        # forecast groups by mechanism: none of them can see it on their own.
        concerns=frozenset({Signal.NETWORK, Signal.DATA, Signal.FAILURE, Signal.CONCURRENCY}),
        phrases=(
            "pool",
            "semaphore",
            "worker count",
            "concurrency ceiling",
            "concurrency limit",
            "max connections",
            "saturat",
            "no timeout",
            "without a timeout",
            "missing timeout",
            "never times out",
            # In an async service the event loop is the pool: work that blocks
            # it holds the same capacity a checked-out connection holds.
            "blocks the event loop",
            "blocking call",
        ),
    ),
    Rule(
        mechanism=Mechanism.SILENT_FAILURE,
        concerns=frozenset({Signal.CRAFT}),
        phrases=(
            "swallow",
            "bare except",
            "broad except",
            "silently",
            "fails silently",
            "returns none",
            "returns an empty",
            "logged and then",
            "passes for a success",
        ),
    ),
    Rule(
        mechanism=Mechanism.SERVICE_COUPLING,
        concerns=frozenset({Signal.CRAFT}),
        phrases=(
            "coupling",
            "coupled",
            "leaks",
            "shallow module",
            "callers must know",
            "reaches into",
            "internals of",
        ),
    ),
    Rule(
        mechanism=Mechanism.SECRET_EXPOSURE,
        concerns=frozenset({Signal.SECURITY}),
        phrases=("secret", "api key", "credential", "password", "hardcoded", "hard-coded"),
    ),
    Rule(
        mechanism=Mechanism.UNTRUSTED_INPUT,
        concerns=frozenset({Signal.SECURITY}),
        phrases=(
            "injection",
            "interpolat",
            "concatenat",
            "parameterised",
            "parameterized",
            "ssrf",
            "escap",
            "sanitis",
            "sanitiz",
            "encoded for",
        ),
    ),
    Rule(
        mechanism=Mechanism.BROKEN_AUTHORISATION,
        concerns=frozenset({Signal.SECURITY}),
        phrases=(
            "authoris",
            "authoriz",
            "another user",
            "signature",
            "issuer",
            "audience",
            "expiry",
            "revoke",
            "rate limit",
        ),
    ),
    Rule(
        mechanism=Mechanism.BLIND_OPERATION,
        concerns=frozenset({Signal.OBSERVABILITY}),
        phrases=(
            "correlation id",
            "request id",
            "trace",
            "cardinality",
            "not logged",
            "no metric",
            "health check",
            "p99",
            "unattributed",
            "cannot be diagnosed",
        ),
    ),
)


class Evidence(BaseModel):
    """One finding, cited so the pressure it supports can be checked.

    The trigger is the phrase from the finding's own sentence that the rule
    matched. It is stored rather than recomputed because a reader auditing a
    forecast should not have to rerun the classifier to see why a finding is
    in a group it does not obviously belong to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    line: int = Field(ge=0)
    symbol: str = Field(min_length=1, max_length=512)
    layer: str = Field(min_length=1, max_length=64)
    trigger: str = Field(min_length=1, max_length=256)

    @property
    def site(self) -> tuple[str, int, str]:
        """Where this was seen. Two findings sharing a site are one thing."""
        return (self.path, self.line, self.symbol)


class Pressure(BaseModel):
    """One mechanism, everything pointing at it, and how that was worked out.

    The evidence and the rule are required fields with no defaults, so there is
    no way to construct a pressure that cannot say where it came from. The
    count, the band and the derivation are computed from the evidence rather
    than stored beside it, which means they cannot drift from it and cannot be
    asserted over it: a caller who wants a bigger number has to produce more
    findings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mechanism: Mechanism
    evidence: tuple[Evidence, ...] = Field(
        min_length=1, description="The findings this was read off. Never empty."
    )
    rule: str = Field(
        min_length=1, max_length=4096, description="Why these findings were grouped together"
    )

    @model_validator(mode="after")
    def _every_piece_of_evidence_is_a_different_site(self) -> Pressure:
        sites = {piece.site for piece in self.evidence}
        if len(sites) != len(self.evidence):
            raise ValueError(
                "two pieces of evidence at one site are one observation: "
                "counting both would inflate the pressure without adding a finding"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def independent_findings(self) -> int:
        """How many separate places the review reached this mechanism from.

        Named for what it counts. It is not a probability, a score or a
        severity, and it is bounded by the review rather than by anything
        about the running system.
        """
        return len(self.evidence)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def band(self) -> Band:
        return Band.for_count(len(self.evidence))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derivation(self) -> str:
        """How this item's number came about, carried in the payload.

        In the payload rather than in a docstring because this is the sentence
        that has to survive the trip to an interface, where a bar next to a
        mechanism name looks exactly like a measurement unless something
        travelling with it says otherwise.
        """
        specialists = sorted({piece.layer for piece in self.evidence})
        files = len({piece.path for piece in self.evidence})
        return (
            f"{_counted(len(self.evidence), 'finding')} from the "
            f"{_listed(tuple(specialists), 'and')} {_plural(len(specialists), 'specialist')} "
            f"across {_counted(files, 'file')}, counted. This is an ordinal reading "
            "of what the review reported: it is not measured, and no experiment in "
            "this repository settles how likely the failure is."
        )


def forecast(findings: Iterable[Finding]) -> tuple[Pressure, ...]:
    """What the findings say is under pressure, most pressed first.

    A finding naming no mechanism in the vocabulary is left out rather than
    swept into an "other" row, because a row nobody can act on still occupies
    the attention of somebody triaging. For the same reason there is no floor
    and no filler: no findings produces no pressures, which reads as silence.
    Silence is the honest output. A forecast that said "no significant risk"
    would be a claim about the service, and what happened is that a review
    found nothing to group.
    """
    cited: dict[Mechanism, dict[tuple[str, int, str], Evidence]] = {}
    applied: dict[Mechanism, Rule] = {}

    for finding in findings:
        matched = _classify(finding)
        if matched is None:
            continue
        rule, trigger = matched
        applied[rule.mechanism] = rule
        piece = Evidence(
            path=finding.path,
            line=finding.line,
            symbol=finding.symbol,
            layer=finding.layer,
            trigger=trigger,
        )
        # setdefault, so the first finding at a site keeps the citation: a
        # second specialist repeating it is agreement, not another site.
        cited.setdefault(rule.mechanism, {}).setdefault(piece.site, piece)

    pressures = [
        Pressure(
            mechanism=mechanism,
            evidence=tuple(sorted(pieces.values(), key=lambda piece: piece.site)),
            rule=applied[mechanism].statement,
        )
        for mechanism, pieces in cited.items()
    ]
    return tuple(sorted(pressures, key=_order))


def _classify(finding: Finding) -> tuple[Rule, str] | None:
    """The one rule this finding counts toward, and the phrase that matched."""
    sentence = finding.mechanism.lower()
    layer = finding.layer.strip().lower()
    for rule in RULES:
        if layer not in rule.specialists:
            continue
        trigger = next((phrase for phrase in rule.phrases if phrase in sentence), None)
        if trigger is not None:
            return rule, trigger
    return None


def _listed(items: tuple[str, ...], conjunction: str) -> str:
    """Names in a sentence somebody could read aloud without stumbling.

    The conjunction is the caller's because the two lists here mean different
    things: a rule accepts any one of several specialists, while a derivation
    reports the ones that actually spoke.
    """
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"


def _counted(count: int, noun: str) -> str:
    return f"{count} {_plural(count, noun)}"


def _order(pressure: Pressure) -> tuple[int, int, str]:
    """Most pressed first, then how many specialists converged on it.

    Two specialists arriving at one mechanism from different concerns is
    stronger evidence than one specialist saying the same thing twice, and it
    is the only tie-break here that is itself derived from the findings. The
    mechanism name breaks the remaining ties so two runs over one report
    produce the same order and stay comparable.
    """
    specialists = {piece.layer for piece in pressure.evidence}
    return (-len(pressure.evidence), -len(specialists), pressure.mechanism.value)
