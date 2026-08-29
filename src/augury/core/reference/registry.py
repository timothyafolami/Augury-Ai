"""Asking PyPI what a package is at, today.

Authoritative rather than searched: the registry's own JSON endpoint is the
source of truth for a version, it needs no key, and it does not have to be
believed the way a search result does.

Every failure is None. A review must work on a train.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

PYPI = "https://pypi.org/pypi/{name}/json"

# A registry that has not answered in this long is not going to. A reviewer
# waiting on a package index is a reviewer nobody runs twice.
TIMEOUT_SECONDS = 4.0

# Small enough to be a polite client of a free service, large enough that a
# thirty-package requirements file resolves in seconds rather than a minute.
POOL_SIZE = 8

# One retry. A second failure is a real answer; a first one usually is not.
ATTEMPTS = 2


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
    import http.client
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "augury/0.1 (+review)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body: str = response.read().decode("utf-8", errors="replace")
            return body
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        # HTTPException is none of the other three -- IncompleteRead and
        # BadStatusLine inherit from it directly -- so a truncated response
        # escaped "every failure is None", left the thread pool mid-batch, and
        # ended the command before the review began.
        return None


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-")


class Registry:
    """PyPI, asked once per package and remembered."""

    def __init__(self, *, fetch: Callable[[str], str | None] = _fetch) -> None:
        self._fetch = fetch
        self._seen: dict[str, PackageFacts | None] = {}

    def facts_for(self, name: str) -> PackageFacts | None:
        key = _canonical(name)
        if key not in self._seen:
            self._seen[key] = self._ask(key)
        return self._seen[key]

    def facts_for_many(self, names: Sequence[str]) -> dict[str, PackageFacts | None]:
        """Ask about several packages at once.

        Sequentially, 34 lookups queue behind each other until the tail
        exceeds the timeout, and nine real packages came back unknown. The
        requests are independent and the work is all waiting, so a small pool
        of threads turns a minute of queueing into a few seconds.
        """
        wanted = [
            key for key in dict.fromkeys(_canonical(n) for n in names) if key not in self._seen
        ]
        if wanted:
            with ThreadPoolExecutor(max_workers=min(POOL_SIZE, len(wanted))) as pool:
                for key, facts in zip(wanted, pool.map(self._ask, wanted), strict=True):
                    self._seen[key] = facts
        return {_canonical(n): self._seen.get(_canonical(n)) for n in names}

    def _get(self, url: str) -> str | None:
        """One GET, retried once.

        A lookup that fails under load and is never retried becomes a
        permanent "unknown" for a package the registry knows perfectly well,
        and unknown reads to a reader like a package with nothing wrong.
        """
        import http.client

        for _ in range(ATTEMPTS):
            try:
                body = self._fetch(url)
            except (OSError, ValueError, http.client.HTTPException):
                # Offline is a normal state, not an error worth surfacing.
                # Widened to match _fetch: a caller may supply its own fetch,
                # and a per-package failure has to stay a per-package None.
                return None
            if body:
                return body
        return None

    def _ask(self, name: str) -> PackageFacts | None:
        body = self._get(PYPI.format(name=name))
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
