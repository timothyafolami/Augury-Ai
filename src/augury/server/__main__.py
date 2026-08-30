"""Run the interface.

    python -m augury.server

One process serves the API and the built frontend, so a demonstration is one
command rather than two and a half.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from augury.server.app import build, serve_frontend

# The Vite build, beside the repository rather than inside the package: it is
# generated, and generated files do not belong in an importable tree.
DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def main() -> None:
    host = os.environ.get("AUGURY_HOST", "127.0.0.1")
    port = int(os.environ.get("AUGURY_PORT", "8000"))
    uvicorn.run(serve_frontend(build(), DIST), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
