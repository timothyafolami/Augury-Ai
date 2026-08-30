"""Reading the documents a repository ships alongside its source.

A reviewer that opens only .py, .ts, .go, .rs, .java and .cpp cannot see the
container that runs as root, the deployment with no memory limit, the workflow
that merges without running the tests or the manifest with no lockfile beside
it. Those are production defects, and none of them is in a source file.

Nothing here consults a model and nothing here judges. It returns an inventory:
what exists, where, and the few facts per kind that change how the source
reads. A .env is never opened, never classified and never inventoried, because
it holds live credentials for the repository under review.
"""

from augury.core.artifacts.reader import (
    Artifact,
    ArtifactKind,
    Inventory,
    holds_live_credentials,
    read_artifacts,
)

__all__ = [
    "Artifact",
    "ArtifactKind",
    "Inventory",
    "holds_live_credentials",
    "read_artifacts",
]
