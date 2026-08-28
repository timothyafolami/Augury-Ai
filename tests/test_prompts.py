"""Prompts are versioned artefacts, not string literals.

The submission has to show "the instructions that shape each agent", and the
improvement changelog needs to cite a prompt change as the cause of a measured
delta. Both require prompts to live in files with their own history.
"""

import pytest

from augury.prompts import PromptError, available, render


def test_renders_a_prompt_with_its_variables() -> None:
    text = render("refiner", finding="the pool is too small", evidence="pool_size=5")

    assert "the pool is too small" in text
    assert "pool_size=5" in text


def test_a_missing_variable_is_an_error_not_a_literal_brace() -> None:
    """Shipping a prompt containing the characters `{module}` to a model is a
    silent quality failure that looks like a bad model rather than a bug."""
    with pytest.raises(PromptError, match="finding"):
        render("refiner", evidence="pool_size=5")


def test_an_unknown_prompt_names_what_is_available() -> None:
    with pytest.raises(PromptError, match="triage"):
        render("no-such-prompt")


def test_every_prompt_on_disk_is_listed() -> None:
    names = available()

    assert "triage" in names
    assert "refiner" in names
    assert "analyst" in names


@pytest.mark.parametrize("name", ["triage", "analyst", "refiner"])
def test_no_prompt_ships_empty(name: str) -> None:
    assert len(render.__doc__ or "") > 0
    from augury.prompts import raw

    assert len(raw(name).strip()) > 200, f"{name} looks like a placeholder"
