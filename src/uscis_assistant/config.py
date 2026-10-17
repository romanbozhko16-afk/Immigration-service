"""Application settings, loaded from environment variables or a local .env file.

Model and effort are global on purpose: every user, free or paid, is served by the
same model at the same effort, so answer quality never depends on the pricing tier.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# claude-fable-5-1 is excluded: it requires 30-day data retention on Anthropic's side,
# which we do not accept for passport data and personal histories.
AllowedModel = Literal["claude-sonnet-5-5", "claude-opus-5-5"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    anthropic_api_key: SecretStr | None = None
    llm_model: AllowedModel = "claude-sonnet-5-5"
    llm_effort: Effort = "high"
    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./data/cases.db"
    # Per-case keys live in a separate database so a backup of the case data alone cannot
    # be decrypted after a case is deleted. Production: a managed KMS.
    keystore_url: str = "sqlite:///./data/keys.db"
    # Master key that wraps the per-case keys (base64, 32 bytes).
    # Generate with: uv run python scripts/generate_master_key.py
    master_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
