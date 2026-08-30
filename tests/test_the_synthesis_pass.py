"""The last pass is the one with the most room to invent, so it is fenced hardest.

Eight specialists each read for one concern and none of them sees the others.
That isolation is deliberate: in a shared conversation one specialist's wrong
claim anchors the next. The cost is that nobody looks at the whole board, and
the most senior observation about a service is usually the one that needed two
specialists to see. Synthesis is the pass that looks.

It is also the pass that consults a model with no source in front of it, which
makes it the easiest place in this tool to start making things up. So these
tests are about what it refuses, in the same spirit as the forecast tests.

Four refusals carry the weight. Nothing connects nothing, and an empty
synthesis is the correct output for a healthy report. An observation cannot
exist without the findings it was built from. Two findings from one specialist
are not a connection, because the whole claim of this pass is that it saw what
one reader could not. And a finding that lives in a file holding live
credentials never reaches the model at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from augury.agents.synthesis import (
    MOST_OBSERVATIONS,
    Citation,
    DraftObservation,
    DraftSynthesis,
    Observation,
    Synthesis,
    catalogue,
    citable,
    how_it_is_deployed,
    what_was_read,
)
from augury.core.adapters.base import Completion, Usage
from augury.core.findings import Finding, Report, Severity
from augury.core.scheduling import Coverage
from augury.core.survey.model import BackingService, Service, Survey
from augury.core.trajectory import Trajectory

T = TypeVar("T", bound=BaseModel)


class _Model:
    """A model that answers with whatever it was handed, and keeps the prompt.

    The prompt is kept because half of what this pass has to guarantee is about
    what never reaches a provider, and that is not visible in the answer.
    """

    model_id = "test-model"

    def __init__(self, answer: DraftSynthesis | None = None) -> None:
        self.calls = 0
        self.prompts: list[str] = []
        self._answer = answer if answer is not None else DraftSynthesis(observations=[])

    @property
    def usage(self) -> Usage:
        return Usage()

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError("the synthesis pass asks for a completion, not a bare object")

    async def call(self, *, prompt: str, schema: type[T]) -> Completion:
        self.calls += 1
        self.prompts.append(prompt)
        return Completion(result=self._answer, usage=Usage(), retries=0)


def _finding(
    path: str = "app/a.py",
    *,
    layer: str = "data",
    symbol: str = "handler",
    line: int = 10,
    mechanism: str = "The session is held open across a network call.",
) -> Finding:
    return Finding(
        path=path,
        line=line,
        layer=layer,
        symbol=symbol,
        mechanism=mechanism,
        severity=Severity.MEDIUM,
        remediation="Close it first.",
    )


def _citation(layer: str = "data", path: str = "app/a.py", line: int = 10) -> Citation:
    return Citation(path=path, line=line, symbol="handler", layer=layer)


TWO_SPECIALISTS = [
    _finding("app/db.py", layer="data", symbol="session"),
    _finding("app/http.py", layer="network", symbol="fetch"),
]

CONNECTED = DraftSynthesis(
    observations=[
        DraftObservation(
            mechanism="The session is held while the outbound call has no deadline, "
            "so a slow dependency parks a connection from the pool.",
            consequence="The database pool is sized for the service's own latency and "
            "is spent by another service's.",
            findings=[1, 2],
        )
    ]
)


def _run(
    model: _Model,
    findings: list[Finding],
    *,
    survey: Survey | None = None,
    coverage: Coverage | None = None,
    trajectory: Trajectory | None = None,
) -> tuple[Observation, ...]:
    report = Report(findings=tuple(findings), coverage=coverage)
    pass_ = Synthesis(model, trajectory=trajectory)
    import asyncio

    return asyncio.run(pass_.observe(report=report, survey=survey or Survey()))


# -- what cannot be built at all ------------------------------------------


def test_an_observation_cannot_be_built_without_the_findings_it_came_from() -> None:
    """The citations are a required field, so there is no observation without
    them. mypy refuses this call too, which is the point."""
    with pytest.raises(ValidationError):
        Observation(  # type: ignore[call-arg]
            mechanism="one shares a pool with the other",
            consequence="the service stalls",
        )


def test_one_finding_is_not_a_connection() -> None:
    with pytest.raises(ValidationError):
        Observation(
            mechanism="one shares a pool with the other",
            consequence="the service stalls",
            citations=(_citation(),),
        )


def test_two_findings_from_one_specialist_are_not_a_connection() -> None:
    """This is the whole claim of the pass. One specialist reporting twice is
    something it could already say on its own, and the report already has it."""
    with pytest.raises(ValidationError, match="specialist"):
        Observation(
            mechanism="both of these are about the same pool",
            consequence="the service stalls",
            citations=(_citation(path="app/a.py"), _citation(path="app/b.py")),
        )


def test_the_same_finding_cited_twice_is_one_finding() -> None:
    same = _citation()
    with pytest.raises(ValidationError):
        Observation(
            mechanism="it connects to itself",
            consequence="the service stalls",
            citations=(same, same),
        )


def test_the_specialists_cannot_be_asserted_over_the_citations() -> None:
    """The number is read off the citations. There is no field to overrule it."""
    with pytest.raises(ValidationError):
        Observation(  # type: ignore[call-arg]
            mechanism="one shares a pool with the other",
            consequence="the service stalls",
            citations=(_citation("data"), _citation("network", path="app/b.py")),
            specialists=("data", "network", "security"),
        )


def test_two_specialists_at_one_site_is_exactly_what_this_pass_is_for() -> None:
    """Unlike the forecast, which counts independent sites, this pass names a
    connection -- and two specialists on one line each holding half of it is
    the observation neither could have written alone."""
    built = Observation(
        mechanism="the session is checked out across the call the timeout is missing from",
        consequence="one slow dependency spends the database pool",
        citations=(_citation("data"), _citation("network")),
    )

    assert built.specialists == ("data", "network")


def test_the_derivation_counts_the_findings_and_names_who_reported_them() -> None:
    built = Observation(
        mechanism="m",
        consequence="c",
        citations=(_citation("data"), _citation("network", path="app/b.py")),
    )

    assert "2 findings" in built.derivation
    assert "data and network" in built.derivation
    assert "not measured" in built.derivation


# -- refusing rather than inventing ---------------------------------------


def test_a_report_with_nothing_to_connect_costs_no_call() -> None:
    """One finding cannot be connected to anything, and the only honest answer
    is already known. Paying a provider for it buys a chance to be wrong."""
    model = _Model(CONNECTED)

    assert _run(model, [_finding()]) == ()
    assert model.calls == 0


def test_one_specialist_speaking_alone_costs_no_call() -> None:
    """Every finding from one specialist means no observation can satisfy the
    rule, whatever the model says. The gate is structural, so it runs first."""
    model = _Model(CONNECTED)
    alone = [
        _finding("app/a.py", layer="data"),
        _finding("app/b.py", layer="data"),
        _finding("app/c.py", layer="data"),
    ]

    assert _run(model, alone) == ()
    assert model.calls == 0


def test_an_empty_answer_is_a_correct_answer() -> None:
    """A synthesis that always finds something is a horoscope."""
    model = _Model(DraftSynthesis(observations=[]))

    assert _run(model, TWO_SPECIALISTS) == ()
    assert model.calls == 1


def test_an_observation_carries_the_findings_it_was_built_from() -> None:
    observations = _run(_Model(CONNECTED), TWO_SPECIALISTS)

    assert len(observations) == 1
    assert {c.path for c in observations[0].citations} == {"app/db.py", "app/http.py"}
    assert observations[0].specialists == ("data", "network")


def test_a_model_citing_one_finding_is_refused_rather_than_promoted() -> None:
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[1])]
        )
    )

    assert _run(model, TWO_SPECIALISTS) == ()


def test_a_citation_of_a_finding_that_does_not_exist_discards_the_whole_thing() -> None:
    """Not trimmed to the citations that resolve. An observation half built
    from something invented is an observation resting on the invented half."""
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[1, 2, 99])]
        )
    )

    assert _run(model, TWO_SPECIALISTS) == ()


def test_a_citation_numbered_from_zero_is_not_silently_read_as_the_first() -> None:
    """The list is numbered from one because that is how it is printed. Zero is
    a number that is not on it."""
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[0, 1])]
        )
    )

    assert _run(model, TWO_SPECIALISTS) == ()


def test_two_citations_of_one_finding_are_refused_as_one_finding() -> None:
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[2, 2])]
        )
    )

    assert _run(model, TWO_SPECIALISTS) == ()


def test_citing_two_findings_from_one_specialist_is_refused() -> None:
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[1, 2])]
        )
    )
    one_concern = [
        _finding("app/a.py", layer="data"),
        _finding("app/b.py", layer="data"),
        _finding("app/c.py", layer="network"),
    ]

    assert _run(model, one_concern) == ()


def test_an_observation_with_nothing_to_say_is_refused() -> None:
    """A mechanism is the field that has to carry the link. Empty, there is no
    link, only two findings printed next to each other."""
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="", consequence="c", findings=[1, 2])]
        )
    )

    assert _run(model, TWO_SPECIALISTS) == ()


def test_a_refusal_is_recorded_rather_than_quietly_dropped(tmp_path: Path) -> None:
    """A pass that deletes its own output is one nobody can audit."""
    journal = tmp_path / "trajectory.jsonl"
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[1, 44])]
        )
    )

    _run(model, TWO_SPECIALISTS, trajectory=Trajectory(journal))

    written = [json.loads(line) for line in journal.read_text().splitlines() if line]
    refusals = [entry for entry in written if entry.get("action") == "refused"]
    assert refusals, "the observation was discarded with no record of why"
    assert "44" in json.dumps(refusals[0]["detail"])


def test_only_a_few_observations_survive(tmp_path: Path) -> None:
    """Past a handful this stops being a senior read of the board and becomes a
    second findings table, which is the artefact it exists to avoid."""
    findings = [
        _finding(f"app/{n}.py", layer="data" if n % 2 else "network", symbol=f"s{n}")
        for n in range(1, 21)
    ]
    model = _Model(
        DraftSynthesis(
            observations=[
                DraftObservation(
                    mechanism=f"mechanism {n}",
                    consequence=f"consequence {n}",
                    findings=[n, n + 1],
                )
                for n in range(1, 20)
            ]
        )
    )
    journal = tmp_path / "trajectory.jsonl"

    observations = _run(model, findings, trajectory=Trajectory(journal))

    assert len(observations) == MOST_OBSERVATIONS
    assert "set aside" in journal.read_text()


# -- what the model is shown ----------------------------------------------


def test_every_finding_reaches_the_model_numbered_and_attributed() -> None:
    model = _Model()

    _run(model, TWO_SPECIALISTS)

    listed = catalogue(tuple(TWO_SPECIALISTS))

    assert listed in model.prompts[0]
    assert "1. [data] `app/db.py:10` `session`" in listed
    assert "2. [network] `app/http.py:10` `fetch`" in listed


def test_the_model_is_told_what_the_review_never_read() -> None:
    """An observation about the service as a whole, drawn from a fifth of it,
    is a claim about the four fifths nobody opened."""
    model = _Model()
    coverage = Coverage(
        analysed=["app/db.py", "app/http.py"],
        skipped={"app/c.py": "budget", "app/d.py": "budget"},
        stopped_because="the budget ran out",
    )

    _run(model, TWO_SPECIALISTS, coverage=coverage)

    prompt = model.prompts[0]
    assert "read 2 modules and did not read 2" in prompt
    assert "stopped because the budget ran out" in prompt


def test_the_deployment_the_survey_found_reaches_the_model() -> None:
    """A pool size is wrong relative to a worker count, and the worker count is
    in the compose command rather than in any file a specialist read."""
    model = _Model()
    survey = Survey(
        services=(
            Service(
                name="worker",
                source_root="backend",
                command="celery -A src.tasks worker --concurrency=16",
                ports=("8000:8000",),
                depends_on=("postgres",),
            ),
        ),
        backing=(BackingService(name="postgres", image="postgres:16", kind="database"),),
    )

    _run(model, TWO_SPECIALISTS, survey=survey)

    prompt = model.prompts[0]
    assert "worker" in prompt
    assert "--concurrency=16" in prompt
    assert "postgres:16" in prompt


def test_the_prompt_says_plainly_that_an_empty_answer_is_correct() -> None:
    """The one instruction that decides whether this pass is honest."""
    from augury.prompts import raw

    prompt = raw("synthesis").lower()

    assert "empty" in prompt
    assert "correct" in prompt or "expected" in prompt


def test_the_prompt_asks_for_no_field_the_schema_lacks() -> None:
    """The analyst prompt once asked for a field the schema did not have. The
    model complied, the schema dropped the answer, and the arm scored zero."""
    import re

    from augury.prompts import raw

    known = set(DraftSynthesis.model_fields) | set(DraftObservation.model_fields)
    asked = {
        name
        for bullet in re.findall(r"^\s*-\s+(`\w+`(?:\s*,\s*`\w+`)*)\s*:", raw("synthesis"), re.M)
        for name in re.findall(r"`(\w+)`", bullet)
    }

    assert asked, "the prompt describes no response fields at all"
    assert asked <= known, f"synthesis.md asks for {sorted(asked - known)}"
    assert known <= asked, f"synthesis.md never describes {sorted(known - asked)}"


# -- the credentials rule -------------------------------------------------

SECRET = "gsk_liveKeyThatMustNeverBeQuotedAnywhere"


@pytest.mark.parametrize(
    "path",
    [".env", ".envrc", ".env.local", ".env.production", "backend/.env", "deploy/.env.staging"],
)
def test_a_finding_in_a_file_holding_live_credentials_never_reaches_the_model(path: str) -> None:
    """A specialist names the path, and the path is a model's output rather
    than ours. Quoting the file back into a prompt would put a reviewed
    repository's credentials into a provider request and a committed cassette.
    """
    model = _Model()
    findings = [
        _finding(path, layer="security", mechanism=f"The key {SECRET} is set here."),
        *TWO_SPECIALISTS,
    ]

    _run(model, findings)

    prompt = model.prompts[0]
    assert SECRET not in prompt
    assert path not in prompt


def test_the_committed_template_is_safe_and_is_kept() -> None:
    """`.env.example` holds no values and names every knob that exists, which
    is half of every configuration defect."""
    kept = citable(
        [_finding(".env.example", layer="security"), _finding("app/db.py", layer="data")]
    )

    assert [f.path for f in kept] == [".env.example", "app/db.py"]


def test_a_refused_finding_cannot_be_cited_by_number_either() -> None:
    """The numbering the model is shown is the numbering it answers in, so a
    refused finding is not merely hidden -- it is not addressable."""
    model = _Model(
        DraftSynthesis(
            observations=[DraftObservation(mechanism="m", consequence="c", findings=[1, 2, 3])]
        )
    )
    findings = [_finding(".env", layer="security"), *TWO_SPECIALISTS]

    assert _run(model, findings) == ()


def test_a_deployment_environment_variable_reaches_the_model_by_name_only() -> None:
    """A compose file sets values as well as names, and one of them is
    routinely a password. The name is the fact worth having."""
    survey = Survey(
        services=(
            Service(
                name="api",
                environment={"DATABASE_URL": f"postgres://app:{SECRET}@db/app", "POOL_SIZE": "5"},
            ),
        )
    )

    said = how_it_is_deployed(survey)

    assert "DATABASE_URL" in said
    assert "POOL_SIZE" in said
    assert SECRET not in said
    assert "5" not in said


def test_a_refusal_quoting_the_model_back_is_redacted_on_its_way_to_the_journal(
    tmp_path: Path,
) -> None:
    """A model call is redacted into the trajectory and a plain record is not,
    so a refusal that quotes the model's own prose has to redact itself.
    Trajectories are committed and handed to judges."""
    journal = tmp_path / "trajectory.jsonl"
    model = _Model(
        DraftSynthesis(
            observations=[
                DraftObservation(
                    mechanism=f"the key {SECRET} links them", consequence="c", findings=[1, 77]
                )
            ]
        )
    )

    _run(model, TWO_SPECIALISTS, trajectory=Trajectory(journal))

    written = journal.read_text()
    assert "refused" in written
    assert SECRET not in written


def test_nothing_under_the_repository_being_reviewed_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This pass reads findings, not files, and this is the test that keeps it
    that way. A `.env` sitting in the repository under review is the file this
    tool must never open, and the cheapest guarantee is a pass with no reason
    to open anything."""
    (tmp_path / ".env").write_text(f"GROQ_API_KEY={SECRET}\n")
    opened: list[str] = []
    real = Path.read_text

    def watched(self: Path, *args: Any, **kwargs: Any) -> str:
        opened.append(str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", watched)
    monkeypatch.chdir(tmp_path)
    model = _Model(CONNECTED)

    _run(model, TWO_SPECIALISTS)

    assert not [path for path in opened if str(tmp_path) in path], f"opened {opened}"
    assert SECRET not in model.prompts[0]


# -- the blocks the prompt is assembled from ------------------------------


def test_a_review_with_no_coverage_recorded_says_so_rather_than_claiming_all() -> None:
    said = what_was_read(None)

    assert "not recorded" in said


def test_a_repository_with_no_deployment_says_so_rather_than_going_silent() -> None:
    said = how_it_is_deployed(Survey())

    assert said.strip()
    assert "no deployment" in said


def test_the_catalogue_numbers_from_one() -> None:
    said = catalogue(tuple(TWO_SPECIALISTS))

    assert said.startswith("1.")
    assert "\n2." in said
