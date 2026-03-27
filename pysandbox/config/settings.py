"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Platform identity
    PYSANDBOX_MASTER_KEY: SecretStr = SecretStr("dev-master-key")
    PYSANDBOX_ENV: str = "dev"
    PYSANDBOX_VERSION: str = "1.0.0"

    # Database (platform metadata — NOT sandbox data)
    DATABASE_URL: SecretStr = SecretStr("sqlite+aiosqlite:///./pysandbox.db")

    # Docker
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    DOCKER_NETWORK_PREFIX: str = "pysb"
    CONTAINER_NAME_PREFIX: str = "pysb"

    # DNS server
    DNS_BIND_HOST: str = "127.0.0.1"
    DNS_PORT_RANGE_START: int = 5300
    DNS_PORT_RANGE_END: int = 5599
    SANDBOX_DNS_DOMAIN: str = "sandbox.local"

    # Port allocation for exposed plugin ports
    HOST_PORT_RANGE_START: int = 20000
    HOST_PORT_RANGE_END: int = 29999

    # Secrets
    SECRET_ENCRYPTION_KEY: SecretStr = SecretStr("")

    # Resource defaults per sandbox
    DEFAULT_SANDBOX_CPU_LIMIT: float = 16.0
    DEFAULT_SANDBOX_MEMORY_LIMIT_GB: float = 32.0
    DEFAULT_SANDBOX_DISK_LIMIT_GB: float = 100.0
    MAX_PLUGINS_PER_SANDBOX: int = 20
    PLUGIN_HEALTH_TIMEOUT_SECONDS: int = 120

    # Agent
    AGENT_IMAGE: str = "pysandbox/pyoz:latest"
    AGENT_CPU_LIMIT: float = 2.0
    AGENT_MEMORY_LIMIT_GB: float = 4.0

    # Event bus
    EVENT_BUS_BACKEND: str = "asyncio"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Observability
    LOG_LEVEL: str = "INFO"
    PROMETHEUS_ENABLED: bool = True
    OTEL_ENDPOINT: str | None = None

    # Vault (optional)
    VAULT_ADDR: str | None = None
    VAULT_TOKEN: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
