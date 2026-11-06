from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required: the API controls the host's WireGuard interfaces, so it never runs unauthenticated.
    api_key: str = Field(min_length=16)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: str = "*"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: object) -> object:
        return v.upper() if isinstance(v, str) else v

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        errors = "; ".join(
            f"{'_'.join(str(part) for part in error['loc']).upper()}: {error['msg']}" for error in exc.errors()
        )
        raise SystemExit(f"Invalid configuration: {errors}") from None


settings = load_settings()
