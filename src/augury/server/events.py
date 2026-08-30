"""The words the interface is allowed to hear.

The stream started as ad hoc dicts built at the call site, which agree with the
interface exactly until someone renames a key. Nothing raises when they stop
agreeing: the browser reads a field that is no longer there, a stage never
lights up, and the run looks like it skipped work it did. That failure is
silent in both directions, which is the worst property a demonstration can have.

So the names live in one enum, each event has one constructor, and the payload
is assembled here rather than at eighteen call sites. A typo is now a
`NameError` at import rather than a bar that never appears.

Two things every event carries. A sequence number, because the interface orders
by it and a gap tells it a step went missing. And a millisecond offset from the
moment the run started, because a waterfall without offsets is a list. Both are
counted and measured, never estimated: the offset is what the clock said, and
the clock is passed in so a test can move it without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# Seconds, from a monotonic source. Monotonic rather than wall clock because a
# machine that resyncs its time mid-review would otherwise draw a bar running
# backwards, and the offsets are the one thing on screen a viewer reads as fact.
Clock = Callable[[], float]


class EventName(StrEnum):
    """Every word the pipeline may say to the interface.

    Dotted `subject.verb`, so the interface can group by subject without being
    handed a second table mapping names to sections.
    """

    REVIEW_STARTED = "review.started"
    SCOUT_STARTED = "scout.started"
    LANGUAGE_DETECTED = "language.detected"
    FRAMEWORK_DETECTED = "framework.detected"
    SERVICE_DETECTED = "service.detected"
    STRUCTURE_DISCOVERED = "structure.discovered"
    MODEL_BUILT = "model.built"
    AGENT_STARTED = "agent.started"
    AGENT_HANDOFF = "agent.handoff"
    AGENT_FINISHED = "agent.finished"
    RESEARCH_STARTED = "research.started"
    RESEARCH_FINISHED = "research.finished"
    FINDING_DETECTED = "finding.detected"
    CONTEXT_UPDATED = "context.updated"
    COVERAGE_COMPUTED = "coverage.computed"
    PREDICTION_GENERATED = "prediction.generated"
    REVIEW_COMPLETED = "review.completed"
    REVIEW_FAILED = "review.failed"


VOCABULARY: frozenset[str] = frozenset(member.value for member in EventName)


@dataclass(frozen=True)
class Event:
    """One thing that happened, numbered and timed.

    Frozen because the sequence number is what the interface trusts to order
    the waterfall, and a number that can be rewritten after the fact orders
    nothing.
    """

    name: EventName
    seq: int
    offset_ms: int
    data: Mapping[str, Any]

    def as_json(self) -> dict[str, Any]:
        """The event as it goes down the wire, in plain JSON types only."""
        return {
            "event": self.name.value,
            "seq": self.seq,
            "offsetMs": self.offset_ms,
            "data": dict(self.data),
        }


class Events:
    """One run's events, in the order the run produced them.

    Held per run rather than globally: two reviews watched at once would
    otherwise share a counter, and each viewer would see a waterfall with half
    its bars belonging to somebody else's repository.
    """

    def __init__(self, *, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        # Read once, here, so every offset is from the start of this review
        # rather than from whatever the clock happened to already be counting.
        self._started = clock()
        self._seq = 0

    # -- the run ----------------------------------------------------------

    def review_started(self, *, root: str, name: str, scope: str, model: str) -> Event:
        """A review of this repository, at this scope, by this model."""
        return self._say(
            EventName.REVIEW_STARTED,
            {"root": root, "name": name, "scope": scope, "model": model},
        )

    def review_completed(self, *, report: Mapping[str, Any]) -> Event:
        return self._say(EventName.REVIEW_COMPLETED, {"report": report})

    def review_failed(self, *, detail: str) -> Event:
        """What broke. A demonstration must say so rather than stop moving."""
        return self._say(EventName.REVIEW_FAILED, {"detail": detail})

    # -- reading the deployment before the code ---------------------------

    def scout_started(self) -> Event:
        return self._say(EventName.SCOUT_STARTED, {})

    def language_detected(self, *, language: str, modules: int) -> Event:
        """`modules` is how many files of it were mapped, not an estimate of
        how much of the repository it is."""
        return self._say(EventName.LANGUAGE_DETECTED, {"language": language, "modules": modules})

    def framework_detected(self, *, framework: str, evidence: str) -> Event:
        """`evidence` is the file that proves it.

        A framework claimed without one is a guess, and this tool does not make
        those. The interface shows the path beside the name for the same
        reason: a reader can open it and disagree.
        """
        return self._say(
            EventName.FRAMEWORK_DETECTED, {"framework": framework, "evidence": evidence}
        )

    def service_detected(
        self, *, service: str, source_root: str, command: str, capacity: int | None
    ) -> Event:
        """One service the repository builds and runs from its own source.

        `capacity` is None when the command declares no ceiling. A worker's
        concurrency lives in its command and nowhere else, so absent it is
        unknown -- and one is a plausible number rather than a measured one.
        """
        return self._say(
            EventName.SERVICE_DETECTED,
            {
                "service": service,
                "sourceRoot": source_root,
                "command": command,
                "capacity": capacity,
            },
        )

    # -- the map ----------------------------------------------------------

    def structure_discovered(
        self, *, modules: int, reachable: int, unreachable: Sequence[str]
    ) -> Event:
        """What the map found, including what no entrypoint reaches.

        The unreachable paths are listed rather than counted, because "nothing
        imports these eleven files" is a claim a reader is entitled to check.
        """
        return self._say(
            EventName.STRUCTURE_DISCOVERED,
            {"modules": modules, "reachable": reachable, "unreachable": unreachable},
        )

    def model_built(self, *, layers: Sequence[Mapping[str, Any]]) -> Event:
        """The system model, entrypoint through to store."""
        return self._say(EventName.MODEL_BUILT, {"layers": layers})

    # -- the specialists --------------------------------------------------

    def agent_started(self, *, agent: str, layer: str, module: str) -> Event:
        return self._say(
            EventName.AGENT_STARTED, {"agent": agent, "layer": layer, "module": module}
        )

    def agent_handoff(self, *, from_agent: str, to_agent: str, why: str) -> Event:
        """Work passing between agents, and what made it pass.

        The parameters are not spelled like the fields because `from` is a
        reserved word. The fields are what the interface reads.
        """
        return self._say(EventName.AGENT_HANDOFF, {"from": from_agent, "to": to_agent, "why": why})

    def agent_finished(self, *, agent: str, findings: int) -> Event:
        return self._say(EventName.AGENT_FINISHED, {"agent": agent, "findings": findings})

    def finding_detected(self, *, finding: Mapping[str, Any]) -> Event:
        return self._say(EventName.FINDING_DETECTED, {"finding": finding})

    # -- what the run looked up, and what it remembered -------------------

    def research_started(self, *, subject: str, source: str) -> Event:
        """A real registry or changelog lookup, named so a reader can repeat it."""
        return self._say(EventName.RESEARCH_STARTED, {"subject": subject, "source": source})

    def research_finished(self, *, subject: str, found: bool) -> Event:
        """`found` says whether the source answered.

        A lookup that fails is silent, correctly, because a review has to work
        offline. Silence is the right behaviour and the wrong report: "checked
        it, it is current" and "could not reach the registry" are opposite
        facts, and the interface may not show one as the other.
        """
        return self._say(EventName.RESEARCH_FINISHED, {"subject": subject, "found": found})

    def context_updated(self, *, what: str, count: int) -> Event:
        """Memory and cache moving, as in `core/memo.py`.

        `what` names the store, `count` is how many entries it holds now. Both
        are read off the store rather than accumulated here, so two watchers
        joining at different moments are told the same number.
        """
        return self._say(EventName.CONTEXT_UPDATED, {"what": what, "count": count})

    # -- what the run concluded -------------------------------------------

    def coverage_computed(self, *, layers: Sequence[Mapping[str, Any]]) -> Event:
        """What each specialist read, and what it did not."""
        return self._say(EventName.COVERAGE_COMPUTED, {"layers": layers})

    def prediction_generated(self, *, items: Sequence[Mapping[str, Any]]) -> Event:
        return self._say(EventName.PREDICTION_GENERATED, {"items": items})

    # ---------------------------------------------------------------------

    def _say(self, name: EventName, data: Mapping[str, Any]) -> Event:
        self._seq += 1
        return Event(
            name=name,
            seq=self._seq,
            offset_ms=round((self._clock() - self._started) * 1000),
            data=_plain(data),
        )


def _plain(value: Any) -> Any:
    """A copy of this payload in plain JSON types.

    Copied because an event is what was true when it fired, and callers hand in
    dicts they go on mutating. Converted because a payload that only turns out
    to be unserialisable when a browser asks for it fails at the least useful
    moment of the run.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, str | bytes):
        return value
    if isinstance(value, Sequence):
        return [_plain(item) for item in value]
    return value
