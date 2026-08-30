"""A forecast is the one thing here nobody measured, so it is fenced hardest.

Every other number this tool publishes was counted or observed. The forecast is
not: it says what is likely to give way, which no experiment in this repository
settles. That makes it the easiest place to quietly start inventing, so these
tests are about what the type refuses rather than about what it computes.

Three refusals matter. Nothing is a forecast of nothing, not a clean bill of
health. A pressure cannot exist without the findings it was read off. And two
findings about one mechanism are one pressure with two pieces of evidence,
because the alternative is a list that grows by restating itself.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from augury.core.findings import Finding, Severity
from augury.core.forecast import Band, Evidence, Mechanism, Pressure, forecast


def _evidence(path: str = "a.py", line: int = 1, symbol: str = "s") -> Evidence:
    return Evidence(path=path, line=line, symbol=symbol, layer="data", trigger="query per")


def _finding(
    path: str,
    mechanism: str,
    *,
    layer: str = "data",
    symbol: str = "handler",
    line: int = 1,
) -> Finding:
    return Finding(
        path=path,
        line=line,
        layer=layer,
        symbol=symbol,
        mechanism=mechanism,
        severity=Severity.MEDIUM,
        remediation="Fix it.",
    )


IN_A_LOOP = "The serializer issues one query per row, so queries per request scales with the page."


def test_no_findings_forecast_nothing() -> None:
    """An empty list is silence, and silence is not the same as safe."""
    assert forecast([]) == ()


def test_a_pressure_cannot_be_built_without_evidence() -> None:
    # mypy refuses this call too, which is the point: the ignore is the record
    # that the type checker catches it before anything reaches an interface.
    with pytest.raises(ValidationError):
        Pressure(  # type: ignore[call-arg]
            mechanism=Mechanism.QUERY_AMPLIFICATION, rule="because I said so"
        )


def test_a_pressure_cannot_be_built_with_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        Pressure(mechanism=Mechanism.QUERY_AMPLIFICATION, rule="because I said so", evidence=())


def test_a_pressure_cannot_be_built_without_the_rule_that_produced_it() -> None:
    """Evidence with no rule is a list of files, not a derivation."""
    with pytest.raises(ValidationError):
        Pressure(  # type: ignore[call-arg]
            mechanism=Mechanism.QUERY_AMPLIFICATION,
            evidence=(_evidence(),),
        )


def test_the_same_mechanism_in_two_files_is_one_item_with_two_pieces_of_evidence() -> None:
    pressures = forecast([_finding("app/a.py", IN_A_LOOP), _finding("app/b.py", IN_A_LOOP)])

    assert len(pressures) == 1
    assert pressures[0].mechanism is Mechanism.QUERY_AMPLIFICATION
    assert len(pressures[0].evidence) == 2
    assert {e.path for e in pressures[0].evidence} == {"app/a.py", "app/b.py"}
    assert pressures[0].independent_findings == 2


def test_the_count_cannot_be_asserted_independently_of_the_evidence() -> None:
    """The number is read off the evidence. There is no field to overrule it."""
    with pytest.raises(ValidationError):
        Pressure(  # type: ignore[call-arg]
            mechanism=Mechanism.QUERY_AMPLIFICATION,
            rule="a data specialist named a query in a loop",
            evidence=(_evidence(),),
            independent_findings=17,
        )


def test_the_same_site_twice_is_one_observation() -> None:
    """Two specialists on one line saw one thing, however loudly."""
    same = [_finding("app/a.py", IN_A_LOOP), _finding("app/a.py", IN_A_LOOP)]

    assert forecast(same)[0].independent_findings == 1


def test_evidence_may_not_repeat_a_site() -> None:
    at = _evidence()
    with pytest.raises(ValidationError):
        Pressure(mechanism=Mechanism.QUERY_AMPLIFICATION, rule="r", evidence=(at, at))


def test_a_finding_naming_no_known_mechanism_is_left_out() -> None:
    """There is no other bucket. An unclassified finding is not a forecast."""
    assert forecast([_finding("app/a.py", "The name of this variable is unhelpful.")]) == ()


def test_a_finding_is_counted_under_one_mechanism_only() -> None:
    """One observation appearing as two pressures is the inflation we refuse."""
    both = _finding(
        "app/a.py",
        "The serializer runs one query per row and the pool cannot serve that many at once.",
    )

    # The sentence answers to two rules a `data` specialist owns. Resolution
    # order settles it, and the finding is spent once.
    assert len(forecast([both])) == 1
    assert forecast([both])[0].mechanism is Mechanism.QUERY_AMPLIFICATION


def test_the_specialist_that_does_not_own_the_concern_does_not_press_on_it() -> None:
    """The layer that owns a concern is the one whose word about it counts."""
    assert forecast([_finding("app/a.py", IN_A_LOOP, layer="observability")]) == ()


def test_every_evidence_names_the_phrase_it_was_read_from() -> None:
    """So a reader can grep the finding and see the rule fire."""
    trigger = forecast([_finding("app/a.py", IN_A_LOOP)])[0].evidence[0].trigger

    assert trigger in IN_A_LOOP.lower()


def test_the_band_is_ordinal_and_rises_with_the_count() -> None:
    one = forecast([_finding("app/a.py", IN_A_LOOP)])[0]
    two = forecast([_finding(f"app/{n}.py", IN_A_LOOP) for n in range(2)])[0]
    three = forecast([_finding(f"app/{n}.py", IN_A_LOOP) for n in range(3)])[0]

    assert one.band is Band.ISOLATED
    assert two.band is Band.REPEATED
    assert three.band is Band.SYSTEMIC
    assert one.band.rung < two.band.rung < three.band.rung


def test_no_field_can_be_read_as_a_probability() -> None:
    """The vocabulary is the guard. A percentage here would be invented."""
    pressure = forecast([_finding("app/a.py", IN_A_LOOP)])[0]
    names = set(pressure.model_dump().keys())

    forbidden = ("probability", "likelihood", "confidence", "percent", "score", "chance", "risk")
    assert not [n for n in names for word in forbidden if word in n]


def test_a_pressure_says_that_it_was_derived_rather_than_measured() -> None:
    derivation = forecast([_finding("app/a.py", IN_A_LOOP)])[0].derivation

    assert "not measured" in derivation


def test_the_most_pressed_mechanism_comes_first() -> None:
    findings = [
        _finding("app/a.py", "Secrets are read from a hardcoded credential.", layer="security"),
        *[_finding(f"app/q{n}.py", IN_A_LOOP) for n in range(3)],
    ]

    pressures = forecast(findings)

    assert [p.mechanism for p in pressures] == [
        Mechanism.QUERY_AMPLIFICATION,
        Mechanism.SECRET_EXPOSURE,
    ]


def test_the_order_is_stable_for_equal_pressure() -> None:
    findings = [
        _finding("app/s.py", "Secrets are read from a hardcoded credential.", layer="security"),
        _finding("app/q.py", IN_A_LOOP),
    ]

    assert forecast(findings) == forecast(list(reversed(findings)))


def test_every_rule_is_owned_by_a_specialist_that_exists() -> None:
    """A rule naming a layer nobody runs is a rule that never fires."""
    from augury.core.forecast import RULES

    for rule in RULES:
        assert rule.specialists, f"{rule.mechanism} is owned by no specialist"
