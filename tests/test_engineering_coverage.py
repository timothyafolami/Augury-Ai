"""How much of the framework a review exercised, and where it must say nothing.

The web interface draws one bar per specialist. A bar is a claim, so the two
failures that matter are drawing a full one for a concern nobody looked at, and
drawing a full one for a concern that does not appear in the repository at all.
The second is the subtle one: "we read all zero of them" is arithmetically 1.0
and reassures a reader about a layer the review never touched.
"""

from __future__ import annotations

import pytest

from augury.core.cartography import ModuleNode, RepoMap, Signal
from augury.core.coverage import Basis, EngineeringCoverage, LayerCoverage, engineering_coverage
from augury.core.findings import Finding, Severity
from augury.core.layers import LAYERS
from augury.core.scheduling import Coverage


def _module(path: str, *signals: Signal) -> ModuleNode:
    return ModuleNode(path=path, loc=20, signals=frozenset(signals))


def _map(*modules: ModuleNode) -> RepoMap:
    return RepoMap(root="/repo", modules=list(modules))


def _read(*paths: str) -> Coverage:
    return Coverage(analysed=list(paths), stopped_because="budget exhausted")


def _finding(layer: str, path: str = "app/api.py") -> Finding:
    return Finding(
        path=path,
        line=1,
        layer=layer,
        symbol="handler",
        mechanism="The session is shared between concurrent requests.",
        remediation="Give each request its own session.",
        severity=Severity.HIGH,
    )


def _row(result: EngineeringCoverage, name: str) -> LayerCoverage:
    return next(row for row in result.layers if row.layer == name)


def test_a_concern_that_appears_nowhere_has_no_number() -> None:
    """The one lie this display can tell.

    Nothing in the repository raises a security signal, so no specialist was
    ever going to be asked about one. Dividing zero reads by zero occurrences
    to get 1.0 draws a full bar under the word Security.
    """
    repo = _map(_module("app/db.py", Signal.DATA))

    result = engineering_coverage(repo, _read("app/db.py"), [])

    security = _row(result, "security")
    assert security.share is None
    assert security.occurrences == ()


def test_a_concern_read_everywhere_it_appears_is_fully_covered() -> None:
    repo = _map(_module("app/db.py", Signal.DATA), _module("app/repo.py", Signal.DATA))

    result = engineering_coverage(repo, _read("app/db.py", "app/repo.py"), [])

    assert _row(result, "data").share == 1.0


def test_a_partially_covered_layer_reports_the_fraction_not_the_count() -> None:
    """Four modules raise the concern and one was read. That is 25%, and the
    three the budget never reached are the point of the number."""
    repo = _map(*(_module(f"app/{n}.py", Signal.SECURITY) for n in range(4)))

    result = engineering_coverage(repo, _read("app/0.py"), [])

    security = _row(result, "security")
    assert security.share == 0.25
    assert len(security.occurrences) == 4
    assert security.reviewed == ("app/0.py",)


def test_a_concern_that_appears_and_was_never_read_reports_zero_not_none() -> None:
    """None means the question does not arise here. Zero means it does and
    nobody answered it. Collapsing them loses the more alarming one."""
    repo = _map(_module("app/queue.py", Signal.DISTRIBUTED))

    result = engineering_coverage(repo, _read(), [])

    assert _row(result, "distributed").share == 0.0


def test_no_layer_claims_more_modules_than_the_map_holds() -> None:
    """Coverage is over modules that exist, so a row cannot cite one that does
    not, nor read one it never counted as an occurrence."""
    repo = _map(
        _module("app/api.py", Signal.ENTRYPOINT, Signal.NETWORK, Signal.DATA),
        _module("app/db.py", Signal.DATA),
        _module("app/empty.py"),
    )
    paths = {module.path for module in repo.modules}

    result = engineering_coverage(repo, _read("app/api.py", "app/db.py", "app/nowhere.py"), [])

    assert result.modules == 3
    for row in result.layers:
        assert len(row.occurrences) <= result.modules
        assert set(row.occurrences) <= paths
        assert set(row.reviewed) <= set(row.occurrences)


def test_a_module_read_for_one_concern_does_not_cover_another() -> None:
    """The denominator is per layer, not per repository. Reading the one file
    that raises both must not close the second layer's other four files."""
    repo = _map(
        _module("app/api.py", Signal.DATA, Signal.SECURITY),
        _module("app/auth.py", Signal.SECURITY),
    )

    result = engineering_coverage(repo, _read("app/api.py"), [])

    assert _row(result, "data").share == 1.0
    assert _row(result, "security").share == 0.5


def test_an_entrypoint_counts_toward_the_network_specialist() -> None:
    """Routing already says an entrypoint is a network concern. Coverage that
    disagreed would report a gap the review does not have."""
    repo = _map(_module("app/main.py", Signal.ENTRYPOINT))

    result = engineering_coverage(repo, _read("app/main.py"), [])

    assert _row(result, "network").share == 1.0


def test_every_specialist_gets_a_row_in_declaration_order() -> None:
    """A layer with nothing to report must render as an absent bar rather than
    vanish, or the framework looks smaller than it is."""
    result = engineering_coverage(_map(_module("app/db.py", Signal.DATA)), _read(), [])

    assert tuple(row.layer for row in result.layers) == tuple(layer.name for layer in LAYERS)


def test_every_row_carries_a_title_the_interface_can_print() -> None:
    result = engineering_coverage(_map(), _read(), [])

    assert _row(result, "observability").title == "Observability"
    assert all(row.title for row in result.layers)


def test_findings_are_counted_against_the_layer_that_raised_them() -> None:
    repo = _map(_module("app/api.py", Signal.SECURITY, Signal.DATA))
    findings = [_finding("security"), _finding("security"), _finding("data")]

    result = engineering_coverage(repo, _read("app/api.py"), findings)

    assert _row(result, "security").findings == 2
    assert _row(result, "data").findings == 1
    assert _row(result, "craft").findings == 0


def test_a_finding_naming_no_specialist_is_counted_not_dropped() -> None:
    """The layer on a finding is what the model wrote, and `drafts` substitutes
    "unknown" when it wrote nothing. Per-layer counts that quietly summed to
    less than the report's own total would be the same fault this tool exists
    to avoid."""
    repo = _map(_module("app/api.py", Signal.SECURITY))

    result = engineering_coverage(repo, _read("app/api.py"), [_finding("unknown")])

    assert result.unattributed_findings == 1
    assert sum(row.findings for row in result.layers) == 0


def test_the_share_says_it_was_inferred_when_nobody_recorded_the_routing() -> None:
    """Without the routing, a read module counts for every layer its signals
    allow, which triage may have narrowed. The row has to admit that."""
    repo = _map(_module("app/api.py", Signal.DATA))

    result = engineering_coverage(repo, _read("app/api.py"), [])

    assert _row(result, "data").basis is Basis.SIGNALLED


def test_recorded_routing_narrows_what_counts_as_read() -> None:
    """Triage narrows the specialists a module's signals allow. Given what it
    chose, the number stops being an upper bound and starts being a count."""
    repo = _map(_module("app/api.py", Signal.DATA, Signal.CONCURRENCY))

    routed = {"app/api.py": ("data",)}
    result = engineering_coverage(repo, _read("app/api.py"), [], routed=routed)

    assert _row(result, "data").share == 1.0
    assert _row(result, "data").basis is Basis.ROUTED
    assert _row(result, "concurrency").share == 0.0


def test_a_module_missing_from_the_recorded_routing_is_not_counted_as_read() -> None:
    """A partial record understates rather than overstates. Overstating is the
    failure this whole number exists to prevent."""
    repo = _map(_module("app/api.py", Signal.DATA), _module("app/db.py", Signal.DATA))

    result = engineering_coverage(repo, _read("app/api.py", "app/db.py"), [], routed={})

    assert _row(result, "data").share == 0.0


def test_the_rows_are_frozen() -> None:
    """A published row is evidence. Nothing downstream may edit it into a
    friendlier number."""
    result = engineering_coverage(_map(_module("app/db.py", Signal.DATA)), _read(), [])

    with pytest.raises(ValueError):
        _row(result, "data").share = 1.0
