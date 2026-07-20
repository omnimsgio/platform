"""Environment-based configuration (ADR-0009)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for gateway, api, and worker."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://omnimsgio:omnimsgio@postgis:5432/omnimsgio",
        description="SQLAlchemy/psycopg DSN for the omnimsgio database",
    )
    redis_url: str = Field(
        default="redis://infra-redis:6379/3",
        description="Redis URL including logical DB index 3",
    )
    redis_key_prefix: str = Field(
        default="omnimsgio:",
        description="Key prefix for queue and event keys",
    )
    redis_queue_outbound: str = Field(
        default="queue:outbound",
        description="Outbound message queue suffix (under redis_key_prefix)",
    )
    api_url: str = Field(
        default="http://api:8000",
        description="Internal API base URL for gateway proxying",
    )
    default_tenant_id: str = Field(
        default="ten_local_dev",
        description="Stub tenant id until API-key tenancy is implemented",
    )
    app_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")

    @property
    def outbound_queue_key(self) -> str:
        prefix = self.redis_key_prefix
        if not prefix.endswith(":"):
            prefix = f"{prefix}:"
        suffix = self.redis_queue_outbound.lstrip(":")
        return f"{prefix}{suffix}"


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings; invalid env fails at first access."""
    return Settings()
