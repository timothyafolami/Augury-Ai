"""Augury as a Model Context Protocol server.

The reviewer is useful inside whatever agent the reader already runs, not only
behind this project's CLI. This package exposes it over MCP so a client can map
a repository, ask what a layer means, and buy a review, without any of them
being a bespoke integration.
"""

from augury.mcp.server import PROTOCOL_VERSION, Server

__all__ = ["PROTOCOL_VERSION", "Server"]
