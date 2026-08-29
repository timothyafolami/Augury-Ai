"""The MCP surface, tested without a subprocess or a network.

The protocol handler is a pure function from request to response, so these
tests exercise the real dispatch rather than a mock of it. Only the reviewer
is substituted, because it is the one part that costs money.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from augury.core.findings import Finding, Report, Severity
from augury.core.scheduling import Budget, Coverage
from augury.core.schemas import Comparator, Prediction
from augury.mcp.server import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    Server,
)


class _StubReviewer:
    """Stands in for the paid pipeline. Records what it was asked to review."""

    def __init__(self) -> None:
        self.roots: list[Path] = []

    async def review(self, repo: object, root: Path) -> Report:
        self.roots.append(root)
        return Report(
            findings=(
                Finding(
                    path="svc/pool.py",
                    line=12,
                    symbol="get_conn",
                    layer="data",
                    severity=Severity.HIGH,
                    mechanism="The pool is created per request, so connections are never reused.",
                    remediation="Create the engine once at module scope and share it.",
                    prediction=Prediction(
                        metric="active_connections",
                        comparator=Comparator.AT_LEAST,
                        value=100,
                        unit="connections",
                        condition="200 concurrent requests",
                    ),
                ),
            ),
            coverage=Coverage(analysed=["svc/pool.py"], stopped_because="budget exhausted"),
            usd=0.004,
            seconds=3.0,
        )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "pool.py").write_text(
        "import sqlalchemy\n\n\ndef get_conn():\n    return sqlalchemy.create_engine('x')\n"
    )
    (tmp_path / "svc" / "api.go").write_text(
        'package svc\n\nimport "net/http"\n\nfunc H(w http.ResponseWriter) {}\n'
    )
    return tmp_path


def test_initialize_reports_the_protocol_version_and_a_tools_capability() -> None:
    result = Server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert result is not None
    assert result["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert "tools" in result["result"]["capabilities"]


def test_a_notification_gets_no_response() -> None:
    # A JSON-RPC notification has no id. Replying to one corrupts the stream.
    assert Server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_every_advertised_tool_has_a_schema_and_a_handler() -> None:
    server = Server()
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    tools = listed["result"]["tools"]
    assert {t["name"] for t in tools} == {"augury_map", "augury_review", "augury_explain"}
    for tool in tools:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"


def test_map_needs_no_api_key_and_reports_languages(repo: Path) -> None:
    # The whole point of separating cartography from review: this is free.
    server = Server(api_key=None)
    out = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "augury_map", "arguments": {"path": str(repo)}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is False
    payload = json.loads(out["result"]["content"][0]["text"])
    assert payload["modules"] == 2
    assert payload["languages"] == {"python": 1, "go": 1}


def test_explain_needs_no_api_key_and_returns_the_layer_brief() -> None:
    out = Server(api_key=None).handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "augury_explain", "arguments": {"topic": "data"}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is False
    text = out["result"]["content"][0]["text"]
    assert "03-data" in text


def test_review_returns_findings_with_their_predictions(repo: Path) -> None:
    server = Server(api_key="test", reviewer_factory=lambda **_: _StubReviewer())
    out = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "augury_review",
                "arguments": {"path": str(repo), "budget_usd": 0.1},
            },
        }
    )
    assert out is not None
    assert out["result"]["isError"] is False
    payload = json.loads(out["result"]["content"][0]["text"])
    assert payload["findings"][0]["prediction"]["metric"] == "active_connections"
    assert payload["usd"] == 0.004


def test_review_without_an_api_key_is_a_tool_error_not_a_crash(repo: Path) -> None:
    # A tool that cannot run must say so inside the result, so the client can
    # show it. Raising here would kill the session instead.
    out = Server(api_key=None).handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "augury_review", "arguments": {"path": str(repo)}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is True
    assert "key" in out["result"]["content"][0]["text"].lower()


def test_an_unknown_method_is_a_json_rpc_error_with_the_right_code() -> None:
    out = Server().handle({"jsonrpc": "2.0", "id": 6, "method": "does/not/exist"})
    assert out is not None
    assert out["error"]["code"] == -32601


def test_a_path_outside_the_allowed_root_is_refused(tmp_path: Path, repo: Path) -> None:
    # The server is handed a root by whoever launched it. A client asking to
    # review somewhere else is a client reading files it was not given.
    server = Server(api_key=None, allowed_root=tmp_path / "nowhere")
    out = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "augury_map", "arguments": {"path": str(repo)}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is True
    assert "outside" in out["result"]["content"][0]["text"].lower()


def test_the_server_speaks_the_protocol_over_a_real_pipe(repo: Path) -> None:
    """End to end: a subprocess, a stdin pipe, and three real requests.

    Every unit test above calls `handle` directly. This is the only test that
    proves the process starts, the transport frames correctly, and a client
    that knows nothing about Augury gets usable answers.
    """
    import subprocess

    requests = "\n".join(
        json.dumps(r)
        for r in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "augury_map", "arguments": {"path": str(repo)}},
            },
        )
    )
    completed = subprocess.run(
        [sys.executable, "-m", "augury.cli", "mcp", "--root", str(repo)],
        input=requests + "\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]

    # Three requests carried an id; the notification must not have been answered.
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert len(replies[1]["result"]["tools"]) == 3
    mapped = json.loads(replies[2]["result"]["content"][0]["text"])
    assert mapped["languages"] == {"go": 1, "python": 1}


# -- hostile input ---------------------------------------------------------


def test_a_top_level_value_that_is_not_an_object_is_an_invalid_request() -> None:
    """A JSON-RPC batch is an array, and several MCP clients send one.

    `handle` did `request.get("id")` unguarded, so any valid JSON that is not
    an object raised AttributeError out of the stdio loop and killed the
    session mid-stream.
    """
    for hostile in (5, "x", [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}], None):
        out = Server().handle(hostile)
        assert out is not None, hostile
        assert out["error"]["code"] == INVALID_REQUEST


def test_malformed_json_is_answered_with_a_parse_error_not_silence(repo: Path) -> None:
    """A truncated request with an id must be told, not left waiting."""
    import subprocess

    completed = subprocess.run(
        [sys.executable, "-m", "augury.cli", "mcp", "--root", str(repo)],
        input='{"jsonrpc": "2.0", "id": 1, "meth\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n',
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert replies[0]["error"]["code"] == PARSE_ERROR
    # And the stream survives: the next well-formed request is still answered.
    assert replies[1]["id"] == 2


def test_a_bad_line_does_not_kill_the_session(repo: Path) -> None:
    """The whole point: one bad request must cost one request, not the run."""
    import subprocess

    completed = subprocess.run(
        [sys.executable, "-m", "augury.cli", "mcp", "--root", str(repo)],
        input='{"jsonrpc":"2.0","id":1,"method":"initialize"}\n5\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n',
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert [r["id"] for r in replies] == [1, 2, 3] or [r["id"] for r in replies] == [1, None, 2]
    assert any(r.get("id") == 2 and "result" in r for r in replies)


def test_a_failure_inside_a_tool_is_not_reported_as_a_missing_method(repo: Path) -> None:
    """`except KeyError` straddled the whole pipeline.

    A KeyError raised anywhere inside a review came back as -32601 "Unknown
    method: tools/call", which many clients treat as "this server has no
    tools" and drop the tool set for the session -- after the review was paid
    for.
    """

    class _Exploding:
        async def review(self, repo: object, root: Path) -> Report:
            raise KeyError("layer-name")

    out = Server(api_key="k", reviewer_factory=lambda **_: _Exploding()).handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "augury_review", "arguments": {"path": str(repo)}},
        }
    )
    assert out is not None
    assert "error" not in out or out["error"]["code"] != METHOD_NOT_FOUND


def test_a_malformed_arguments_shape_is_a_tool_error_not_a_protocol_error(repo: Path) -> None:
    out = Server(api_key=None).handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "augury_map", "arguments": ["/etc"]},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is True


def test_an_explicit_zero_budget_is_not_silently_turned_into_the_default(repo: Path) -> None:
    """`float(args.get("budget_usd") or DEFAULT)` read an explicit 0 as absent."""
    seen: list[float] = []

    class _Recording:
        async def review(self, repo: object, root: Path) -> Report:
            return Report()

    def factory(**kwargs: Budget) -> _Recording:
        seen.append(kwargs["budget"].usd)
        return _Recording()

    out = Server(api_key="k", reviewer_factory=factory).handle(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "augury_review", "arguments": {"path": str(repo), "budget_usd": 0}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is True
    assert seen == [], "a zero budget must be refused, never quietly raised to the default"


def test_a_client_cannot_exceed_the_launcher_s_spending_ceiling(repo: Path) -> None:
    """The root is fixed by the launcher; so must the money be.

    The client here is a language model, and the tool description is written to
    persuade it that reviewing is worthwhile.
    """
    seen: list[float] = []

    class _Recording:
        async def review(self, repo: object, root: Path) -> Report:
            return Report()

    def factory(**kwargs: Budget) -> _Recording:
        seen.append(kwargs["budget"].usd)
        return _Recording()

    server = Server(api_key="k", reviewer_factory=factory, max_budget_usd=0.10)
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "augury_review",
                "arguments": {"path": str(repo), "budget_usd": 1_000_000_000},
            },
        }
    )
    assert seen == [0.10]


def test_a_symlink_out_of_the_root_is_refused(tmp_path: Path, repo: Path) -> None:
    """The boundary survived replacing resolve() with absolute(); this fails it."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "escape").symlink_to(repo, target_is_directory=True)

    out = Server(api_key=None, allowed_root=root).handle(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "augury_map", "arguments": {"path": str(root / "escape")}},
        }
    )
    assert out is not None
    assert out["result"]["isError"] is True
    assert "outside" in out["result"]["content"][0]["text"].lower()
