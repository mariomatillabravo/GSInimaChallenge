"""Typed application settings, read from environment variables and an optional ``.env`` file."""

from typing import Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
