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
        default="http://omnimsgio-api:8000",
        description="Internal API base URL for gateway proxying (unique DNS; avoid bare api)",
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
    meta_app_id: str = Field(
        default="",
        description="Meta App ID for Embedded Signup code exchange (META_APP_ID)",
    )
    meta_graph_api_version: str = Field(
        default="v21.0",
        description="Graph API version for Meta WhatsApp calls (META_GRAPH_API_VERSION)",
    )
    sentry_dsn: str = Field(
        default="",
        description="Optional Sentry DSN; when set, API captures exceptions (SENTRY_DSN)",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="Fixed-window API key rate limit (requests per minute)",
    )
    cors_allowed_origins: str = Field(
        default="https://app.omnimsg.io,https://omnimsgio-app.localhost",
        description=(
            "Comma-separated browser Origins allowed for CORS on the gateway "
            "(portal Embedded Signup). Env: CORS_ALLOWED_ORIGINS"
        ),
    )
    app_version: str = Field(default="0.1.0")
    app_env: str = Field(
        default="development",
        description="Runtime environment label (APP_ENV: development|production|…)",
    )
    git_sha: str = Field(
        default="unknown",
        description="Build git SHA (GIT_SHA); unknown in local/dev",
    )
    build_date: str = Field(
        default="unknown",
        description="Image/build date ISO-ish string (BUILD_DATE)",
    )
    openapi_contract_path: str = Field(
        default="",
        description="Optional absolute path to openapi.yaml (OPENAPI_CONTRACT_PATH)",
    )
    admin_username: str = Field(
        default="",
        description="Ops admin Basic username (ADMIN_USERNAME); empty disables admin",
    )
    admin_password: str = Field(
        default="",
        description="Ops admin Basic password (ADMIN_PASSWORD); empty disables admin",
    )
    admin_read_only: bool = Field(
        default=False,
        description="When true, admin rejects all writes server-side (ADMIN_READ_ONLY)",
    )
    admin_allowed_cidrs: str = Field(
        default="127.0.0.1/32",
        description=(
            "Comma-separated CIDRs for Traefik IP allowlist on /admin "
            "(ADMIN_ALLOWED_CIDRS)"
        ),
    )
    admin_api_key_grace_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description=(
            "Grace window (hours) for two-step API key rotation "
            "(ADMIN_API_KEY_GRACE_HOURS); old key stays valid until expiry"
        ),
    )
    log_level: str = Field(default="INFO")

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_username.strip() and self.admin_password)

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

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
