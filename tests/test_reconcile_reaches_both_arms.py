"""Reconciliation is deterministic and free, so both arms get it.

`reconcile` merges findings that collide on one construct. It was applied to
the pipeline arm only. That is not cosmetic: `_strictest` keeps a prediction
over none, so merging an unfalsifiable finding into a falsifiable one at the
same (path, symbol) removes an observation from the denominator of
`falsifiable_precision`. The baseline kept both.

It costs no model call, so there was never a budget reason to withhold it.
"""

from __future__ import annotations

import ast
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "src" / "augury" / "agents"


def _calls_reconcile(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "reconcile"
        for node in ast.walk(tree)
    )


def test_both_reviewers_reconcile() -> None:
    for arm in ("augury.py", "baseline.py"):
        assert _calls_reconcile(AGENTS / arm), f"{arm} does not reconcile its findings"
