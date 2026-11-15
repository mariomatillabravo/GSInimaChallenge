"""Typed application settings, read from environment variables and an optional ``.env`` file."""

from typing import Self

from pydantic import PositiveFloat, PositiveInt, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.measurements import Aggregation


class Settings(BaseSettings):
    """Runtime configuration. Each field maps to an upper-case environment variable.

    Only values that change between environments live here. Business rules from the challenge
    statement (such as the Europe/Madrid output time zone) are constants in the domain layer.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = False
    """Serve recorded AEMET responses instead of calling the real API (no API key needed)."""

    aemet_api_key: SecretStr | None = None
    """Personal AEMET OpenData API key. Never logged: ``SecretStr`` hides it in reprs."""

    aemet_base_url: str = "https://opendata.aemet.es/opendata"
    aemet_timeout_seconds: PositiveFloat = 30.0
    """Timeout of each HTTP request to AEMET."""
    aemet_max_attempts: PositiveInt = 3
    """Attempts per monthly window when AEMET fails transiently (network, 429, 5xx)."""

    # Maximum requested range per aggregation level, which keeps every response bounded in size.
    max_range_days_none: PositiveInt = 31
    """About 4,500 ten-minute records."""
    max_range_days_hourly: PositiveInt = 366
    """About 8,800 hourly rows."""
    max_range_days_daily: PositiveInt = 3660
    """About 3,700 daily rows (ten years)."""
    max_range_days_monthly: PositiveInt | None = None
    """No practical limit: a monthly series stays small."""

    def max_range_days(self, aggregation: Aggregation) -> int | None:
        """Maximum range, in days, allowed for an aggregation level (``None`` = unlimited)."""
        return {
            Aggregation.NONE: self.max_range_days_none,
            Aggregation.HOURLY: self.max_range_days_hourly,
            Aggregation.DAILY: self.max_range_days_daily,
            Aggregation.MONTHLY: self.max_range_days_monthly,
        }[aggregation]

    @field_validator("aemet_api_key", mode="before")
    @classmethod
    def _blank_key_is_missing(cls, value: object) -> object:
        """Treat ``AEMET_API_KEY=`` (as in ``.env.example``) the same as an unset variable."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _require_key_outside_demo_mode(self) -> Self:
        """Fail fast at startup instead of failing on the first request to AEMET."""
        if not self.demo_mode and self.aemet_api_key is None:
            raise ValueError(
                "AEMET_API_KEY is required when DEMO_MODE is false. "
                "Set DEMO_MODE=true to run with recorded data instead."
            )
        return self
