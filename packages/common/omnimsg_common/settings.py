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
    redis_queue_inbound: str = Field(
        default="queue:inbound",
        description="Inbound webhook queue suffix (under redis_key_prefix)",
    )
    api_url: str = Field(
        default="http://api:8000",
        description="Internal API base URL for gateway proxying",
    )
    default_tenant_id: str = Field(
        default="ten_local_dev",
        description="Local seed tenant id (scripts/seed-local-tenant.sh)",
    )
    redis_events_delivery: str = Field(
        default="events:delivery",
        description="Delivery event list suffix (under redis_key_prefix)",
    )
    meta_verify_token: str = Field(
        default="",
        description="Meta WhatsApp webhook hub.verify_token (META_VERIFY_TOKEN)",
    )
    meta_app_secret: str = Field(
        default="",
        description="Meta app secret for X-Hub-Signature-256 (META_APP_SECRET)",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="Fixed-window API key rate limit (requests per minute)",
    )
    app_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")

    def _prefixed_key(self, suffix: str) -> str:
        prefix = self.redis_key_prefix
        if not prefix.endswith(":"):
            prefix = f"{prefix}:"
        return f"{prefix}{suffix.lstrip(':')}"

    @property
    def outbound_queue_key(self) -> str:
        return self._prefixed_key(self.redis_queue_outbound)

    @property
    def inbound_queue_key(self) -> str:
        return self._prefixed_key(self.redis_queue_inbound)

    @property
    def delivery_events_key(self) -> str:
        return self._prefixed_key(self.redis_events_delivery)

    def rate_limit_key(self, api_key_id: str) -> str:
        return self._prefixed_key(f"rl:{api_key_id}")


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings; invalid env fails at first access."""
    return Settings()
