"""The prompt that writes an experiment, and the schema it must fill.

A prompt asking for a field the schema lacks drove falsifiable precision to
0.000 once. The same check applies here, and it matters more: this prompt's
output is executed.
"""

from __future__ import annotations

from augury.prompts import raw, render


def test_the_prompt_renders_with_the_variables_the_generator_supplies() -> None:
    text = render(
        "experiment",
        path="app/api.py",
        symbol="list_orders",
        mechanism="A query per row.",
        metric="queries_per_request",
        comparator="at_least",
        value="40",
        unit="queries",
        condition="50 rows",
        language="python",
        source="def list_orders(): ...",
    )

    assert "queries_per_request" in text
    assert "list_orders" in text


def test_it_asks_for_exactly_the_schema_fields() -> None:
    from augury.core.proving.generator import GeneratedExperiment

    prompt = raw("experiment")
    for field in GeneratedExperiment.model_fields:
        assert f"`{field}`" in prompt, f"the prompt never mentions {field}"


def test_it_forbids_the_network_because_the_output_is_executed() -> None:
    prompt = raw("experiment").lower()

    assert "no network" in prompt
    assert "no credentials" in prompt


def test_it_carries_the_broken_experiment_checklist() -> None:
    """The lesson this project paid for four times, handed to the generator."""
    prompt = raw("experiment").lower()

    assert "broken rather than a prediction wrong" in prompt
    assert "measured the scheduler" in prompt
    assert "self-throttles" in prompt


def test_it_says_the_measurement_is_the_last_line() -> None:
    """The runner reads the last number, so the writer has to know that."""
    assert "last line" in raw("experiment").lower()
