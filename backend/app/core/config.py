from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mediora"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str
    postgres_user: str = "mediora"
    postgres_password: str = "mediora_pass"
    postgres_db: str = "mediora_db"

    redis_url: str = "redis://redis:6379/0"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Phase 4: Recovery & Scheduling
    ttl_sweep_interval_seconds: int = 5
    ttl_warning_threshold_seconds: int = 10
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    recovery_scan_on_startup: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def set_celery_defaults(self) -> "Settings":
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url
        return self


settings = Settings()

