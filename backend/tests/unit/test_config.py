"""Unit tests for the application settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.measurements import Aggregation
from app.main import create_app


def test_demo_mode_does_not_require_an_api_key() -> None:
    settings = Settings(_env_file=None, demo_mode=True)

    assert settings.aemet_api_key is None


def test_real_mode_without_api_key_fails_fast() -> None:
    with pytest.raises(ValidationError, match="AEMET_API_KEY is required"):
        Settings(_env_file=None, demo_mode=False)


def test_blank_api_key_counts_as_missing() -> None:
    with pytest.raises(ValidationError, match="AEMET_API_KEY is required"):
        Settings(_env_file=None, demo_mode=False, aemet_api_key="   ")


def test_api_key_is_never_shown_in_representations() -> None:
    settings = Settings(_env_file=None, aemet_api_key="super-secret-value")

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.aemet_api_key)
    assert settings.aemet_api_key is not None
    assert settings.aemet_api_key.get_secret_value() == "super-secret-value"


def test_settings_are_read_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")

    assert Settings(_env_file=None).demo_mode is True


def test_settings_are_read_from_an_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEMO_MODE=false\nAEMET_API_KEY=key-from-file\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.demo_mode is False
    assert settings.aemet_api_key is not None
    assert settings.aemet_api_key.get_secret_value() == "key-from-file"


def test_range_limits_per_aggregation_level() -> None:
    settings = Settings(_env_file=None, demo_mode=True, max_range_days_none=7)

    assert settings.max_range_days(Aggregation.NONE) == 7
    assert settings.max_range_days(Aggregation.HOURLY) == 366
    assert settings.max_range_days(Aggregation.DAILY) == 3660
    assert settings.max_range_days(Aggregation.MONTHLY) is None


def test_app_refuses_to_start_without_valid_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Run from an empty folder so that no .env file is found.
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError, match="AEMET_API_KEY is required"):
        create_app()
