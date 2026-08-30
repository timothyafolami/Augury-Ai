"""The interface's API. Nothing here is a mock of a review.

The discovery endpoint runs the real Surveyor and Cartographer, which cost
nothing and take a second, so the tree and the services are on screen before
any money is spent. The review endpoint runs the real pipeline and streams the
real trajectory.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from augury.server.app import build


def _client() -> TestClient:
    return TestClient(build())


def test_discovery_reports_the_services_the_compose_file_declares() -> None:
    """The free half of the review, and the part that opens the demo."""
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "eval/cases/B01-orders-service/repo"})

    assert answer.status_code == 200
    assert "services" in answer.json()


def test_discovery_reports_the_module_tree() -> None:
    with _client() as client:
        found = client.post(
            "/api/discover", json={"path": "eval/cases/B01-orders-service/repo"}
        ).json()

    assert found["modules"], "no modules mapped"
    assert any(m["path"].endswith(".py") for m in found["modules"])


def test_discovery_reports_which_languages_were_found() -> None:
    with _client() as client:
        found = client.post(
            "/api/discover", json={"path": "eval/cases/B01-orders-service/repo"}
        ).json()

    assert found["languages"], "no languages reported"


def test_a_path_outside_the_allowed_roots_is_refused() -> None:
    """The server reads whatever it is pointed at, so it is pointed narrowly.

    A demo that will run on someone else's machine must not accept
    `/etc` or `~/.ssh` from a text box.
    """
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "/etc"})

    assert answer.status_code == 400


def test_a_path_that_climbs_out_with_dots_is_refused() -> None:
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "eval/../../../etc"})

    assert answer.status_code == 400


def test_the_stages_endpoint_names_the_pipeline_the_code_runs() -> None:
    with _client() as client:
        stages = client.get("/api/stages").json()

    assert [s["key"] for s in stages] == ["survey", "map", "schema", "specialists", "report"]


def test_a_missing_path_says_so_rather_than_failing_opaquely() -> None:
    with _client() as client:
        answer = client.post("/api/discover", json={"path": "eval/cases/nope"})

    assert answer.status_code == 404


def test_starting_a_review_returns_something_to_watch() -> None:
    with _client() as client:
        started = client.post(
            "/api/review",
            json={"path": "eval/cases/B01-orders-service/repo", "budget": 0.02},
        )

    assert started.status_code == 200
    assert started.json()["runId"]


def test_a_run_that_was_never_started_has_no_stream() -> None:
    with _client() as client:
        answer = client.get("/api/runs/nope/events")

    assert answer.status_code == 404


def test_a_run_that_was_never_started_has_no_report() -> None:
    with _client() as client:
        answer = client.get("/api/runs/nope/report")

    assert answer.status_code == 404


def test_the_stream_is_server_sent_events() -> None:
    """Chosen over websockets because the traffic is one-way and this
    reconnects by itself when a laptop lid closes mid-demo."""
    with _client() as client:
        run_id = client.post(
            "/api/review",
            json={"path": "eval/cases/B01-orders-service/repo", "budget": 0.02},
        ).json()["runId"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
            assert stream.headers["content-type"].startswith("text/event-stream")


def test_a_review_of_a_refused_path_is_refused_before_it_starts() -> None:
    with _client() as client:
        answer = client.post("/api/review", json={"path": "/etc"})

    assert answer.status_code == 400


def test_the_built_interface_is_served_when_it_has_been_built(tmp_path: Path) -> None:
    """One process serves both in production, so a demo needs one command."""
    from augury.server.app import serve_frontend

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>augury</title>", encoding="utf-8")

    with TestClient(serve_frontend(build(), dist)) as client:
        assert client.get("/").status_code == 200


def test_a_missing_build_is_a_development_machine_not_an_error() -> None:
    """Vite runs separately in development; the API must still start."""
    from augury.server.app import serve_frontend

    app = serve_frontend(build(), Path("/nonexistent/dist"))

    with TestClient(app) as client:
        assert client.get("/api/stages").status_code == 200


def test_the_report_carries_engineering_coverage_per_layer() -> None:
    """The interface draws a bar per specialist, and a bar with no basis
    beside it looks exactly like a measurement."""
    from augury.core.coverage import engineering_coverage
    from augury.core.scheduling import Coverage

    from augury.core.cartography.mapper import Cartographer

    repo = Cartographer(Path("eval/cases/B01-orders-service/repo")).map()
    computed = engineering_coverage(repo, Coverage(analysed=[]), [])

    assert computed.layers, "no layers reported"
    assert all(row.basis for row in computed.layers), "a row with no stated basis"


def test_a_layer_nothing_touches_reports_no_share_rather_than_a_full_bar() -> None:
    """We looked at all zero of them is not a reassuring fact."""
    from augury.core.coverage import engineering_coverage
    from augury.core.cartography.mapper import Cartographer
    from augury.core.scheduling import Coverage

    repo = Cartographer(Path("eval/cases/B01-orders-service/repo")).map()
    computed = engineering_coverage(repo, Coverage(analysed=[]), [])

    empty = [row for row in computed.layers if row.appears_in == 0]
    assert all(row.share is None for row in empty)


def test_a_forecast_item_can_never_be_built_without_its_evidence() -> None:
    """The one property that keeps a forecast from becoming a horoscope."""
    import pytest
    from pydantic import ValidationError

    from augury.core.forecast import Mechanism, Pressure

    with pytest.raises(ValidationError):
        Pressure(mechanism=list(Mechanism)[0], evidence=(), rule="because")
