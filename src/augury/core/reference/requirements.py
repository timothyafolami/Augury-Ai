"""What the repository says it depends on.

Read from the files people actually write, in the spellings they write them.
Parsed rather than resolved: running a resolver would install the repository
under review, and a reviewer must never execute what it is reading.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# `name[extra]==1.2.3 ; python_version < "3.12"` and every simpler shape.
_REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[[^\]]*\])?"
    r"\s*(?:(?P<op>[=<>!~^]+)\s*(?P<version>[0-9][^\s,;]*))?"
)


def requirements_of(root: Path) -> dict[str, str]:
    """Package name to the version it is pinned at, empty where unpinned."""
    found: dict[str, str] = {}
    for path in sorted(Path(root).glob("requirements*.txt")):
        found.update(_from_requirements(path))
    pyproject = Path(root) / "pyproject.toml"
    if pyproject.is_file():
        found.update(_from_pyproject(pyproject))
    return found


def _from_requirements(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        name, version = _parse(stripped)
        if name:
            found[name] = version
    return found


def _from_pyproject(path: Path) -> dict[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, ValueError):
        return {}

    declared: list[str] = list(data.get("project", {}).get("dependencies", []) or [])
    optional = data.get("project", {}).get("optional-dependencies", {}) or {}
    for group in optional.values():
        declared.extend(group)

    found: dict[str, str] = {}
    for requirement in declared:
        name, version = _parse(str(requirement))
        if name:
            found[name] = version
    return found


def _parse(requirement: str) -> tuple[str, str]:
    match = _REQUIREMENT.match(requirement)
    if match is None:
        return "", ""
    return match.group("name").lower().replace("_", "-"), match.group("version") or ""
