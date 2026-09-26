"""Application settings. Everything comes from environment variables / ``.env``; nothing sensitive has a default."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_PREFIX = "/api/v1"
APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    """Runtime configuration (see ``.env.example`` for every variable)."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    real_data_mode: bool = False
    auth_mode: Literal["none", "api_key", "oidc"] = "none"
    api_keys: SecretStr = SecretStr("")  # "name:role:sha256hex,name2:role:sha256hex"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_jwks_url: str = ""
    oidc_audience: str = ""
    oidc_role_claim: str = "role"

    hsts_enabled: bool = False
    request_timeout_seconds: int = 30
    max_concurrent_jobs: int = 10

    log_format: Literal["json", "text"] = "json"
    log_file: str = ""

    storage_backend: Literal["local", "s3"] = "local"
    data_path: str = "./var/data"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = ""
    aws_access_key_id: SecretStr = SecretStr("")
    aws_secret_access_key: SecretStr = SecretStr("")

    database_url: str = ""
    redis_url: str = ""

    rate_limit_per_minute: int = Field(default=240, ge=1)
    max_body_bytes: int = Field(default=1_000_000, ge=1_024)
    ml_device: Literal["auto", "cuda", "cpu"] = "auto"
    model_backend: Literal["baseline", "onnx", "pytorch"] = "baseline"
    audit_log_path: str = "./var/audit.log"
    log_level: str = "INFO"
    demo_seed: int = Field(default=7, ge=0, le=1_000_000)
    demo_members: int = Field(default=10, ge=2, le=30)
    git_sha: str | None = None

    @model_validator(mode="after")
    def validate_mode_flags(self) -> Settings:
        if self.real_data_mode and self.demo_mode:
            raise ValueError("DEMO_MODE must be false when REAL_DATA_MODE is true")
        if self.env == "production" and self.demo_mode:
            raise ValueError("DEMO_MODE must be false in production")
        return self

    @property
    def data_mode(self) -> Literal["real", "demo"]:
        """Return the effective data mode based on current flags."""
        if self.real_data_mode:
            return "real"
        return "demo"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
