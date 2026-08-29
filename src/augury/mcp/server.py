"""The MCP surface: three tools, two of which cost nothing.

`handle` is a pure function from one JSON-RPC request to one response, so the
protocol is testable without a subprocess, a socket, or a client. The stdio
loop in `serve` is the only part that touches IO and it contains no decisions.

Two design points are worth stating because they are the reason this exists at
all rather than being a wrapper around one `review` call:

**Mapping and explaining need no API key.** Cartography is deterministic and
the layer briefs are files on disk, so a client can map a repository and read
what a concern means for free. Only `augury_review` spends money, and it says
what it spent.

**The root is fixed by whoever launched the server, not chosen by the client.**
An MCP client is driven by a language model, and a model that can name any path
can read any file on the machine. The launcher supplies the boundary.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from augury.core.cartography import Cartographer
from augury.core.cartography.languages import EXTENSIONS
from augury.core.findings import Report
from augury.core.layers import LAYERS
from augury.core.metrics import METRICS
from augury.core.scheduling import Budget

# The revision of the protocol this server implements. Declared rather than
# echoed back from the client, so a mismatch surfaces at initialize.
PROTOCOL_VERSION = "2024-11-05"

SERVER_NAME = "augury"
SERVER_VERSION = "0.1.0"

METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603

# A review over MCP is interactive: someone is waiting for it. The default is
# small on purpose, and the client can raise it per call.
DEFAULT_BUDGET_USD = 0.05


class _Reviewer(Protocol):
    """What this server needs from the pipeline. Nothing more."""

    async def review(self, repo: Any, root: Path) -> Report: ...


def _default_reviewer(**kwargs: Any) -> _Reviewer:
    """Built lazily so importing this module never requires a provider."""
    from augury.agents.augury import AuguryReviewer
    from augury.core.adapters.provider import build_model
    from augury.core.settings import load_settings

    settings = load_settings()
    model = build_model(settings.spec, api_key=settings.api_key)
    return AuguryReviewer(model, budget=kwargs["budget"])


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "augury_map",
        "description": (
            "Map a repository without reading it with a model: modules per language, "
            "import graph fan-in, which engineering concerns each file touches, and "
            "which files were skipped and why. Deterministic, free, and needs no API "
            "key. Run this before augury_review to see what a review would cost."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to map. Must be inside this server's root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "augury_review",
        "description": (
            "Review a repository for production failure modes under a dollar budget. "
            "Returns findings that each carry a falsifiable prediction -- a metric, a "
            "comparator, a number with a unit and the condition it holds under -- so "
            "each one can be checked by measurement rather than believed. Costs money "
            "and reports what it spent. On the project's own evaluation this is not "
            "measurably better than sending the whole repository to one prompt; it is "
            "the predictions, the budget and the coverage record that differ."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to review. Must be inside this server's root.",
                },
                "budget_usd": {
                    "type": "number",
                    "description": f"Ceiling on spend. Defaults to {DEFAULT_BUDGET_USD}.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "augury_explain",
        "description": (
            "Explain one of the eight engineering concerns Augury reviews for "
            "(concurrency, network, data, distributed, failure, observability, "
            "security, craft), or list the metrics a prediction may be written in. "
            "Free, and needs no API key."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "A concern name, or 'metrics' for the prediction vocabulary.",
                }
            },
            "required": ["topic"],
        },
    },
)


class ToolFailure(Exception):
    """Something the client asked for that cannot be done.

    Reported inside the tool result rather than as a JSON-RPC error, because a
    protocol error means the request was malformed and a tool failure means the
    request was fine and the answer is no. Clients show the two differently.
    """


class Server:
    """Dispatches MCP requests. Owns no IO."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        allowed_root: Path | None = None,
        reviewer_factory: Callable[..., _Reviewer] = _default_reviewer,
    ) -> None:
        self._api_key = api_key
        self._root = allowed_root.resolve() if allowed_root else None
        self._reviewer_factory = reviewer_factory

    # -- protocol ---------------------------------------------------------

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """One request in, one response out. None for a notification."""
        request_id = request.get("id")
        method = request.get("method", "")

        # A JSON-RPC notification carries no id and must not be answered.
        if request_id is None:
            return None

        try:
            result = self._dispatch(method, request.get("params") or {})
        except ToolFailure as failure:
            return _ok(request_id, _tool_error(str(failure)))
        except KeyError:
            return _error(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}")
        except Exception as exc:  # pragma: no cover - defensive
            return _error(request_id, INTERNAL_ERROR, str(exc))
        return _ok(request_id, result)

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        if method == "tools/list":
            return {"tools": list(TOOLS)}
        if method == "tools/call":
            return self._call(params.get("name", ""), params.get("arguments") or {})
        raise KeyError(method)

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "augury_map":
            return _tool_ok(self._map(self._resolve(arguments.get("path", ""))))
        if name == "augury_explain":
            return _tool_ok(self._explain(str(arguments.get("topic", ""))), raw=True)
        if name == "augury_review":
            budget = float(arguments.get("budget_usd") or DEFAULT_BUDGET_USD)
            return _tool_ok(self._review(self._resolve(arguments.get("path", "")), budget))
        raise ToolFailure(f"Unknown tool: {name}")

    # -- boundary ---------------------------------------------------------

    def _resolve(self, raw_path: str) -> Path:
        """Resolve a client-supplied path inside the launcher's root."""
        if not raw_path:
            raise ToolFailure("A path is required.")
        path = Path(raw_path).expanduser().resolve()
        if self._root is not None and not path.is_relative_to(self._root):
            raise ToolFailure(
                f"Refusing {path}: outside the root this server was launched with ({self._root})."
            )
        if not path.exists():
            raise ToolFailure(f"No such path: {path}")
        return path

    # -- tools ------------------------------------------------------------

    def _map(self, path: Path) -> dict[str, Any]:
        repo = Cartographer(path).map()
        languages: dict[str, int] = {}
        concerns: dict[str, int] = {}
        for module in repo.modules:
            language = EXTENSIONS[Path(module.path).suffix.lower()].value
            languages[language] = languages.get(language, 0) + 1
            for signal in module.signals:
                concerns[signal.value] = concerns.get(signal.value, 0) + 1
        return {
            "root": repo.root,
            "modules": len(repo.modules),
            "languages": dict(sorted(languages.items())),
            "concerns": dict(sorted(concerns.items())),
            "context_files": sorted(repo.context),
            "unparsed": repo.unparsed,
            "skipped": repo.skipped,
        }

    def _explain(self, topic: str) -> str:
        key = topic.strip().lower()
        if key in {"metrics", "metric", "vocabulary"}:
            lines = ["Metrics a prediction may be written in:", ""]
            lines += [f"- {name}: {description}" for name, description in METRICS.items()]
            return "\n".join(lines)
        for layer in LAYERS:
            if layer.name == key:
                return (
                    f"# {layer.name}\n\n"
                    f"Source: practice lab layer {layer.lab_layer}\n"
                    f"Routed by signals: {', '.join(sorted(s.value for s in layer.signals))}\n\n"
                    f"{layer.brief}"
                )
        known = ", ".join(layer.name for layer in LAYERS)
        raise ToolFailure(f"Unknown topic '{topic}'. Known concerns: {known}, or 'metrics'.")

    def _review(self, path: Path, budget_usd: float) -> dict[str, Any]:
        if not self._api_key:
            raise ToolFailure(
                "augury_review needs a provider API key. Set AUGURY_API_KEY (or "
                "GROQ_API_KEY) in the environment this server was launched from. "
                "augury_map and augury_explain work without one."
            )
        repo = Cartographer(path).map()
        reviewer = self._reviewer_factory(budget=Budget(usd=budget_usd))
        report = asyncio.run(reviewer.review(repo, path))
        return {
            "usd": report.usd,
            "seconds": report.seconds,
            # Coverage is optional on Report, so a review that recorded none
            # reports an empty list rather than inventing full coverage.
            "analysed": list(report.coverage.analysed) if report.coverage else [],
            "stopped_because": report.coverage.stopped_because if report.coverage else "",
            "dropped": [{"symbol": d.symbol, "reason": d.reason} for d in report.dropped],
            "findings": [
                {
                    "path": finding.path,
                    "line": finding.line,
                    "symbol": finding.symbol,
                    "layer": finding.layer,
                    "severity": finding.severity.value,
                    "mechanism": finding.mechanism,
                    "prediction": None
                    if finding.prediction is None
                    else {
                        "metric": finding.prediction.metric,
                        "comparator": finding.prediction.comparator.value,
                        "value": finding.prediction.value,
                        "unit": finding.prediction.unit,
                        "condition": finding.prediction.condition,
                    },
                }
                for finding in report.findings
            ],
        }


# -- envelopes ------------------------------------------------------------


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_ok(payload: Any, *, raw: bool = False) -> dict[str, Any]:
    text = payload if raw else json.dumps(payload, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


# -- transport ------------------------------------------------------------


def serve(server: Server) -> None:  # pragma: no cover - exercised by the CLI
    """Newline-delimited JSON-RPC over stdio. Contains no decisions."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
