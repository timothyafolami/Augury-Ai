"""DeepSeek as a provider, chosen from the environment like any other.

It is OpenAI-compatible, so the adapter needs a base URL and a price table
rather than a new client. The reason to add it is the reason the ModelSpec is
configuration in the first place: running one evaluation across providers is
how you find out whether a result depends on the model or on the architecture
around it.

Priced at peak rates. DeepSeek charges half off-peak, and a cost that is
sometimes half what was reported is a cost nobody can plan against -- so this
reports the number that is never an underestimate.
"""

from __future__ import annotations

import pytest

from augury.core.adapters.base import ModelSpec
from augury.core.adapters.pricing import pricing_for
from augury.core.adapters.provider import OPENAI_COMPATIBLE_BASE_URLS, build_model
from augury.core.settings import API_KEY_VARIABLES, load_settings

MODELS = ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"]


@pytest.mark.parametrize("model", MODELS)
def test_every_deepseek_model_is_priced(model: str) -> None:
    """An unpriced model is refused at construction, so it must be here."""
    rates = pricing_for(model)

    assert rates.usd_per_1m_input > 0
    assert rates.usd_per_1m_output > 0


def test_flash_is_cheaper_than_pro() -> None:
    flash, pro = pricing_for("deepseek-v4-flash"), pricing_for("deepseek-v4-pro")

    assert flash.usd_per_1m_input < pro.usd_per_1m_input
    assert flash.usd_per_1m_output < pro.usd_per_1m_output


def test_pricing_is_the_peak_rate_never_the_discounted_one() -> None:
    """Off-peak is half. Reporting the half would understate every run."""
    assert pricing_for("deepseek-v4-flash").usd_per_1m_output == pytest.approx(1.32)
    assert pricing_for("deepseek-v4-pro").usd_per_1m_output == pytest.approx(3.96)


def test_deepseek_is_reached_over_the_openai_compatible_path() -> None:
    assert "deepseek" in OPENAI_COMPATIBLE_BASE_URLS
    assert OPENAI_COMPATIBLE_BASE_URLS["deepseek"] == "https://api.deepseek.com"


def test_the_key_variable_is_the_one_deepseek_documents() -> None:
    assert API_KEY_VARIABLES["deepseek"] == "DEEPSEEK_API_KEY"


def test_a_client_can_be_built_for_deepseek() -> None:
    model = build_model(ModelSpec(provider="deepseek", model="deepseek-v4-flash"), api_key="k")

    assert model.model_id == "deepseek-v4-flash"


def test_the_environment_selects_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of the exercise: pick provider and model without editing code."""
    monkeypatch.setenv("AUGURY_PROVIDER", "deepseek")
    monkeypatch.setenv("AUGURY_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    settings = load_settings()

    assert settings.spec.provider == "deepseek"
    assert settings.spec.model == "deepseek-v4-pro"
    assert settings.api_key == "sk-test"


def test_a_missing_deepseek_key_says_which_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    from augury.core.settings import SettingsError

    monkeypatch.setenv("AUGURY_PROVIDER", "deepseek")
    monkeypatch.setenv("AUGURY_MODEL", "deepseek-v4-flash")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("AUGURY_ENV_FILE", "/nonexistent")

    with pytest.raises(SettingsError, match="DEEPSEEK_API_KEY"):
        load_settings()
