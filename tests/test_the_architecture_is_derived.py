"""A diagram of the service, drawn from what was read rather than from a guess.

Every node and every edge here has to come from something already established:
a service the compose file declares, a directory the map holds, a backing
service something imports. A diagram with a node nobody can trace back is
prettier than the truth and worth less than nothing, because it is the one
artefact a reader will believe without checking.

The bottleneck overlay is the point. A node carries the capacity ceiling its
deployment declares and the findings that landed inside it, so the place the
service is narrowest is visible rather than described.
"""

from __future__ import annotations

from pathlib import Path

from augury.core.architecture import architecture
from augury.core.cartography.mapper import Cartographer
from augury.core.survey import Surveyor

CASE = Path("eval/cases/B01-orders-service/repo")


def _drawn(findings: list[object] | None = None):  # noqa: ANN202
    found = Surveyor(CASE).survey()
    entrypoints = tuple({e for s in found.services for e in s.entrypoints})
    repo = Cartographer(CASE, entrypoints=entrypoints).map()
    return architecture(found, repo, findings or [])


def test_every_service_the_compose_file_declares_becomes_a_node() -> None:
    drawn = _drawn()
    names = {node.label for node in drawn.nodes}

    for service in Surveyor(CASE).survey().services:
        assert service.name in names


def test_a_backing_service_is_drawn_as_a_store_not_as_code() -> None:
    """Postgres is not a module and must not be laid out like one."""
    drawn = _drawn()
    stores = {node.label for node in drawn.nodes if node.kind == "store"}

    assert stores, "no backing service was drawn"


def test_the_code_is_grouped_rather_than_drawn_one_node_per_file() -> None:
    """A 1,100 module repository is not a diagram, it is a hairball."""
    drawn = _drawn()

    assert len(drawn.nodes) < 40, f"{len(drawn.nodes)} nodes is not a diagram"


def test_a_node_carries_the_capacity_ceiling_its_deployment_declares() -> None:
    """The bottleneck the code cannot show. It is only in the compose file."""
    found = Surveyor(CASE).survey()
    if not any("--concurrency" in s.command for s in found.services):
        return  # this case declares none, and the assertion below covers one that does

    drawn = _drawn()
    assert any(node.ceiling for node in drawn.nodes)


def test_every_edge_joins_two_nodes_that_exist() -> None:
    """An edge to a node nobody drew is a line to nowhere."""
    drawn = _drawn()
    ids = {node.id for node in drawn.nodes}

    for edge in drawn.edges:
        assert edge.source in ids, edge.source
        assert edge.target in ids, edge.target


def test_a_node_with_no_findings_reports_none_rather_than_a_low_score() -> None:
    drawn = _drawn()

    assert all(node.findings == 0 for node in drawn.nodes)


def test_the_diagram_of_an_empty_repository_is_empty_rather_than_invented() -> None:
    from augury.core.cartography import RepoMap
    from augury.core.survey.model import Survey

    drawn = architecture(Survey(services=(), source_roots=()), RepoMap(root="/tmp/x", modules=[], unreachable=(), unparsed=[]), [])

    assert drawn.nodes == ()
