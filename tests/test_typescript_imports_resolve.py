"""A TypeScript project has an import graph, and it was always empty.

`_index` registered only files whose suffix is `.py`, with the reasoning that
only Python names are dotted module paths. That is true, and it left every
other language with no internal edges at all: fan-in zero on every module,
nothing reachable from an entrypoint, the scheduler's boost for a module that
imports something already found defective permanently inert, and no edges in
the architecture diagram.

Found by adding a TypeScript case: every module in it reported `fan_in=0`
while `index.ts` plainly imports `./routes/orders.js`. The Python cases could
not show it, because Python is the one language that resolved.

The `.js` specifier naming a `.ts` file is not a quirk to tolerate: it is what
TypeScript requires under ESM, so it is the ordinary spelling in exactly the
kind of repository this tool is aimed at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.cartography.mapper import Cartographer


def _project(root: Path, files: dict[str, str]) -> Cartographer:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Cartographer(root)


def _edges(root: Path, files: dict[str, str]) -> dict[str, set[str]]:
    repo = _project(root, files).map()
    return {module.path: set(module.imports) for module in repo.modules}


def test_a_js_specifier_resolves_to_the_ts_file_it_names(tmp_path: Path) -> None:
    """The ESM convention TypeScript requires, and the common case."""
    edges = _edges(
        tmp_path,
        {
            "src/index.ts": 'import { db } from "./db.js";\nexport const x = db;\n',
            "src/db.ts": "export const db = 1;\n",
        },
    )

    assert edges["src/index.ts"] == {"src/db.ts"}


def test_an_extensionless_specifier_resolves(tmp_path: Path) -> None:
    edges = _edges(
        tmp_path,
        {
            "src/index.ts": 'import { db } from "./db";\nexport const x = db;\n',
            "src/db.ts": "export const db = 1;\n",
        },
    )

    assert edges["src/index.ts"] == {"src/db.ts"}


def test_a_parent_directory_specifier_resolves(tmp_path: Path) -> None:
    edges = _edges(
        tmp_path,
        {
            "src/routes/orders.ts": 'import { db } from "../db.js";\nexport const o = db;\n',
            "src/db.ts": "export const db = 1;\n",
        },
    )

    assert edges["src/routes/orders.ts"] == {"src/db.ts"}


def test_a_directory_specifier_resolves_to_its_index(tmp_path: Path) -> None:
    edges = _edges(
        tmp_path,
        {
            "src/app.ts": 'import { r } from "./routes/index.js";\nexport const a = r;\n',
            "src/routes/index.ts": "export const r = 1;\n",
        },
    )

    assert edges["src/app.ts"] == {"src/routes/index.ts"}


def test_a_bare_specifier_is_not_an_internal_edge(tmp_path: Path) -> None:
    """`express` is a dependency, not a module of this repository."""
    edges = _edges(
        tmp_path,
        {
            "src/index.ts": 'import express from "express";\nexport const a = express;\n',
            "src/express.ts": "export const decoy = 1;\n",
        },
    )

    assert edges["src/index.ts"] == set(), "a bare specifier must not match a local file by name"


def test_fan_in_counts_the_importers(tmp_path: Path) -> None:
    """Which is what the scheduler ranks by, and what was always zero."""
    repo = _project(
        tmp_path,
        {
            "src/a.ts": 'import { d } from "./db.js";\nexport const a = d;\n',
            "src/b.ts": 'import { d } from "./db.js";\nexport const b = d;\n',
            "src/db.ts": "export const d = 1;\n",
        },
    ).map()

    by_path = {module.path: module for module in repo.modules}

    assert by_path["src/db.ts"].fan_in == 2


@pytest.mark.parametrize("suffix", [".tsx", ".jsx", ".js", ".mjs"])
def test_the_other_extensions_resolve_too(tmp_path: Path, suffix: str) -> None:
    edges = _edges(
        tmp_path,
        {
            "src/index.ts": 'import { d } from "./widget.js";\nexport const a = d;\n',
            f"src/widget{suffix}": "export const d = 1;\n",
        },
    )

    assert edges["src/index.ts"] == {f"src/widget{suffix}"}


def test_python_resolution_is_unchanged(tmp_path: Path) -> None:
    """The dotted path is still the Python rule; nothing here replaces it."""
    edges = _edges(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from pkg.b import thing\n\nvalue = thing\n",
            "pkg/b.py": "thing = 1\n",
        },
    )

    assert "pkg/b.py" in edges["pkg/a.py"]
