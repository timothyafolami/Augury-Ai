"""Both arms must be shown the same facts.

An adversarial review found that the pipeline was given the deployment
configuration and the baseline was not, while both were graded on predictions
that depend on it -- the analyst brief says outright that "a pool size is wrong
relative to a worker count, and the worker count is here rather than in the
file you are reading". The baseline was asked for the same arithmetic without
the numbers.

It was not a budget constraint: the baseline prompt used 16,640 of its 120,000
characters. There was room for the deployment files seven times over.

These tests exist so a future change cannot reintroduce an asymmetry quietly.
"""

from pathlib import Path

import pytest

from augury.agents.baseline import BaselineReviewer
from augury.core.adapters.base import Usage
from augury.core.cartography import Cartographer
from augury.core.metrics import vocabulary
from augury.prompts import raw


def repo_with_deployment(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "app" / "db.py").write_text("import sqlalchemy\n\npool_size = 5\n")
    (tmp_path / "Dockerfile").write_text('CMD ["uvicorn", "app:app", "--workers", "8"]\n')
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n    build: .\n")
    return tmp_path


def test_both_arms_are_shown_the_deployment_configuration(tmp_path: Path) -> None:
    """The worker count is the other half of half the defects in the taxonomy."""
    root = repo_with_deployment(tmp_path)
    repo = Cartographer(root).map()

    reviewer = BaselineReviewer(_never_called())  # type: ignore[arg-type]
    included, _ = reviewer._select(repo, root)
    prompt = "\n\n".join(included)

    assert "--workers" in prompt, "the baseline cannot do the arithmetic it is asked for"
    assert "Dockerfile" in prompt


@pytest.mark.parametrize("prompt", ["analyst", "baseline"])
def test_both_arms_receive_the_same_metric_vocabulary(prompt: str) -> None:
    assert "{metrics}" in raw(prompt)
    assert vocabulary()


@pytest.mark.parametrize("prompt", ["analyst", "baseline"])
def test_both_arms_are_told_what_a_finding_must_carry(prompt: str) -> None:
    """Asking one arm for a number and the other for an opinion would decide
    the falsifiable-precision comparison before either ran."""
    text = raw(prompt).lower()

    assert "unit" in text
    assert "condition" in text
    assert "prediction" in text


def test_neither_arm_is_told_which_defects_were_seeded() -> None:
    """A prompt naming a case's defect would measure instruction-following."""
    for name in ("analyst", "baseline", "triage"):
        text = raw(name).lower()
        assert "b01" not in text
        assert "seeded" not in text


class _never_called:
    """Selection consults no model, so this one is never asked for anything."""

    model_id = "unused"

    async def structured(self, *, prompt: str, schema: type) -> object:  # pragma: no cover
        raise AssertionError("selection must not call a model")

    async def call(self, *, prompt: str, schema: type) -> object:  # pragma: no cover
        raise AssertionError("selection must not call a model")

    @property
    def usage(self) -> Usage:
        return Usage()
