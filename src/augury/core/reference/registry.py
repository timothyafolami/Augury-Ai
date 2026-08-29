"""Asking PyPI what a package is at, today.

Authoritative rather than searched: the registry's own JSON endpoint is the
source of truth for a version, it needs no key, and it does not have to be
believed the way a search result does.

Every failure is None. A review must work on a train.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

PYPI = "https://pypi.org/pypi/{name}/json"

# A registry that has not answered in this long is not going to. A reviewer
# waiting on a package index is a reviewer nobody runs twice.
TIMEOUT_SECONDS = 4.0


@dataclass(frozen=True)
class PackageFacts:
    """What the registry says about a package right now."""

    name: str
    latest: str
    summary: str
    released: str = ""

    def behind(self, pinned: str) -> str | None:
        """How far a pin is from current, or None if it is current or absent."""
        if not pinned or pinned == self.latest:
            return None
        return f"{pinned} pinned, {self.latest} current"


def _fetch(url: str) -> str | None:
    """One GET, no dependencies, every failure swallowed."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "augury/0.1 (+review)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body: str = response.read().decode("utf-8", errors="replace")
            return body
    except (urllib.error.URLError, OSError, ValueError):
        return None


class Registry:
    """PyPI, asked once per package and remembered."""

    def __init__(self, *, fetch: Callable[[str], str | None] = _fetch) -> None:
        self._fetch = fetch
        self._seen: dict[str, PackageFacts | None] = {}

    def facts_for(self, name: str) -> PackageFacts | None:
        key = name.lower().replace("_", "-")
        if key not in self._seen:
            self._seen[key] = self._ask(key)
        return self._seen[key]

    def _ask(self, name: str) -> PackageFacts | None:
        try:
            body = self._fetch(PYPI.format(name=name))
        except OSError:
            # Offline is a normal state, not an error worth surfacing.
            return None
        if not body:
            return None
        try:
            payload = json.loads(body)
            info = payload["info"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

        version = str(info.get("version") or "")
        releases = payload.get("releases") or {}
        files = releases.get(version) or []
        released = ""
        if files and isinstance(files, list):
            released = str(files[0].get("upload_time_iso_8601") or "")[:10]

        return PackageFacts(
            name=str(info.get("name") or name),
            latest=version,
            summary=str(info.get("summary") or ""),
            released=released,
        )
