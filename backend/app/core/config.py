from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment or an ignored local env file."""

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "native-dev"
    app_name: str = "The Company Agent"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_secret_key: str = Field(default="native-dev-only-change-this", min_length=16)
    session_cookie_name: str = "company_agent_session"
    session_idle_seconds: int = 8 * 60 * 60
    session_absolute_seconds: int = 7 * 24 * 60 * 60
    login_max_failures: int = 5
    login_lockout_seconds: int = 15 * 60

    mysql_url: str = "mysql+asyncmy://127.0.0.1:3306/company_agent"
    mysql_pool_size: int = 5
    mysql_max_overflow: int = 5

    redis_url: str = "redis://127.0.0.1:6379/3"
    redis_stream_name: str = "company-agent-runs"
    redis_consumer_group: str = "company-agent-workers"

    elasticsearch_url: str = "http://127.0.0.1:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index_prefix: str = "company-agent-knowledge"

    local_storage_root: Path = Path("data/storage")
    local_storage_max_bytes: int = 5 * 1024**3

    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_model: str = "agnes-2.5-flash"
    agnes_api_key: str | None = None

    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_api_key: str | None = None
    siliconflow_vision_model: str = "Qwen/Qwen3.5-4B"
    siliconflow_embedding_model: str = "BAAI/bge-m3"
    siliconflow_embedding_dimensions: int = 1024
    allow_external_chat: bool = False
    allow_external_vision: bool = False
    allow_external_embedding: bool = False
    allow_trusted_sandbox: bool = True
    allow_arbitrary_python: bool = False
    sandbox_timeout_seconds: int = 30
    sandbox_max_output_bytes: int = 10 * 1024 * 1024

    web_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]

    @field_validator("web_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_native_dev(self) -> bool:
        return self.app_env in {"native-dev", "test"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
