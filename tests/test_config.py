import pytest
from pydantic import ValidationError

from uscis_assistant.config import Settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    # Ignore the developer's real .env and environment.
    monkeypatch.chdir(tmp_path)
    for name in ("LLM_MODEL", "LLM_EFFORT", "ANTHROPIC_API_KEY", "APP_ENV", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_default_model_is_sonnet():
    assert Settings().llm_model == "claude-sonnet-5-5"


def test_model_can_be_switched_to_opus(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5-5")
    assert Settings().llm_model == "claude-opus-5-5"


@pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-haiku-5-5", "gpt-5"])
def test_disallowed_models_are_rejected(monkeypatch, model):
    monkeypatch.setenv("LLM_MODEL", model)
    with pytest.raises(ValidationError):
        Settings()


def test_no_per_tier_model_settings():
    # Free and paid users must get identical quality: there is one model, one effort.
    tier_fields = [f for f in Settings.model_fields if "tier" in f or "plan" in f]
    assert tier_fields == []


def test_api_key_is_not_exposed_in_repr(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    settings = Settings()
    assert "sk-test-not-a-real-key" not in repr(settings)
    assert settings.anthropic_api_key.get_secret_value() == "sk-test-not-a-real-key"
