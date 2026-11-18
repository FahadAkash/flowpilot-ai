"""Typed application configuration using pydantic-settings.

Follows python-skills/web-app-architecture and llm-features conventions:
- Single BaseSettings model validated at boot
- Refuses default secret key in production
- Normalizes postgres:// URLs to postgresql+asyncpg://
- Supports both FLOWPILOT_* prefixed vars and standard env var names (DATABASE_URL, LM_STUDIO_*, etc.)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_SECRET = "dev-only-change-in-production-flowpilot-secret-key-32bytes"


def normalize_async_db_url(url: str) -> str:
    """Normalize postgres:// or postgresql:// URLs to postgresql+asyncpg://."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    """Centralized FlowPilot AI runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FLOWPILOT_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "FlowPilot AI"
    env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("FLOWPILOT_ENV", "ENVIRONMENT"),
    )
    debug: bool = False
    secret_key: str = Field(
        default=DEFAULT_DEV_SECRET,
        validation_alias=AliasChoices("FLOWPILOT_SECRET_KEY", "SECRET_KEY"),
    )
    access_token_expire_minutes: int = Field(
        default=60 * 24,
        validation_alias=AliasChoices(
            "FLOWPILOT_ACCESS_TOKEN_EXPIRE_MINUTES",
            "ACCESS_TOKEN_EXPIRE_MINUTES",
        ),
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./flowpilot_dev.db",
        validation_alias=AliasChoices("FLOWPILOT_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("FLOWPILOT_REDIS_URL", "REDIS_URL"),
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("FLOWPILOT_CELERY_BROKER_URL", "CELERY_BROKER_URL"),
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        validation_alias=AliasChoices(
            "FLOWPILOT_CELERY_RESULT_BACKEND",
            "CELERY_RESULT_BACKEND",
        ),
    )
    storage_dir: str = Field(
        default="./storage/documents",
        validation_alias=AliasChoices("FLOWPILOT_STORAGE_DIR", "STORAGE_DIR"),
    )
    max_upload_size_mb: int = Field(
        default=50,
        validation_alias=AliasChoices("FLOWPILOT_MAX_UPLOAD_SIZE_MB", "MAX_UPLOAD_SIZE_MB"),
    )
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
        alias="FLOWPILOT_CORS_ORIGINS",
    )

    # LLM Gateway (mock | lmstudio | openai | gemini | anthropic | ollama)
    llm_provider: Literal["mock", "lmstudio", "openai", "gemini", "anthropic", "ollama"] = Field(
        default="mock",
        validation_alias=AliasChoices("FLOWPILOT_LLM_PROVIDER", "LLM_PROVIDER"),
    )
    tier1_model: str = "gpt-4o-mini"
    tier2_model: str = "gpt-4o-mini"
    tier3_model: str = "gpt-4o"

    # Local LM Studio (OpenAI-compatible chat + real neural embeddings)
    lm_studio_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("FLOWPILOT_LM_STUDIO_BASE_URL", "LM_STUDIO_BASE_URL"),
    )
    lm_studio_chat_model: str = Field(
        default="google/gemma-4-12b-qat",
        validation_alias=AliasChoices("FLOWPILOT_LM_STUDIO_CHAT_MODEL", "LM_STUDIO_CHAT_MODEL"),
    )
    lm_studio_embedding_model: str = Field(
        default="text-embedding-nomic-embed-text-v1.5@q8_0",
        validation_alias=AliasChoices(
            "FLOWPILOT_LM_STUDIO_EMBEDDING_MODEL",
            "LM_STUDIO_EMBEDDING_MODEL",
            "EMBEDDING_MODEL_NAME",
        ),
    )
    embedding_dimensions: int = Field(
        default=768,
        validation_alias=AliasChoices("FLOWPILOT_EMBEDDING_DIMENSIONS", "EMBEDDING_DIMENSION"),
    )

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias="OLLAMA_BASE_URL",
    )

    # Production Guardrails defaults
    max_steps: int = 12
    max_agent_calls: int = 15
    max_tokens_per_workflow: int = 10_000
    execution_timeout_seconds: int = 90
    max_retries: int = 2
    max_tool_calls_per_agent: int = 5
    max_escalations: int = 1
    default_confidence_threshold: float = 0.80
    global_daily_budget_usd: float = 100.0
    default_user_daily_budget_usd: float = 15.0
    max_context_tokens: int = 6_000

    # Circuit breaker defaults
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: int = 60

    # Background jobs
    use_celery_worker: bool = False

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        """Refuse insecure defaults in production and normalize DB URLs."""
        self.database_url = normalize_async_db_url(self.database_url)
        if self.env == "production":
            if not self.secret_key or self.secret_key == DEFAULT_DEV_SECRET:
                raise ValueError(
                    "FLOWPILOT_SECRET_KEY must be explicitly set to a strong secret in production."
                )
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are disallowed in production.")
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "production"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
