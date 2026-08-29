"""Telling a specialist which versions it is looking at.

"SQLAlchemy sessions are not concurrency-safe" is a claim about a version. The
model answers from its training cutoff; the repository pins something; the
registry knows what is current. All three together cost nothing per call and
remove the guess.

Only the packages the module imports, because thirty-four dependencies in every
specialist prompt is noise priced per call.
"""

from __future__ import annotations

from typing import Protocol

from augury.core.reference.registry import PackageFacts


class _Registry(Protocol):
    def facts_for(self, name: str) -> PackageFacts | None: ...


# Import name to distribution name, where they differ. `import jwt` installs
# PyJWT, and reading the import literally reports a pinned dependency as
# unpinned.
DISTRIBUTION_OF = {
    "jwt": "pyjwt",
    "yaml": "pyyaml",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "jose": "python-jose",
    "multipart": "python-multipart",
    "attr": "attrs",
    "OpenSSL": "pyopenssl",
    "serial": "pyserial",
    "google": "google-api-python-client",
    "redis": "redis",
}


def describe_versions(imports: set[str], *, pinned: dict[str, str], registry: _Registry) -> str:
    """One line per third-party package this module uses."""
    if not imports:
        return "This file imports no third-party packages."

    lines: list[str] = []
    for name in sorted(imports):
        key = DISTRIBUTION_OF.get(name, name.lower().replace("_", "-"))
        version = pinned.get(key, "")

        # Only packages this repository declares. A name it does not depend on
        # may still exist on the registry -- `src` does -- and reporting that
        # version would be invented context in the one block whose purpose is
        # to replace a guess with a fact.
        if key not in pinned:
            lines.append(
                f"- `{name}`: not declared in this repository's dependencies, "
                "so its version is unknown here"
            )
            continue

        facts = registry.facts_for(key)

        if version and facts and facts.latest and version != facts.latest:
            lines.append(f"- `{name}`: {version} installed, {facts.latest} current")
        elif version and facts and version == facts.latest:
            lines.append(f"- `{name}`: {version}, current")
        elif version:
            lines.append(f"- `{name}`: {version} installed")
        elif facts and facts.latest:
            lines.append(f"- `{name}`: not pinned, {facts.latest} current")
        else:
            lines.append(f"- `{name}`: version not declared anywhere in this repository")

    return "\n".join(lines)
