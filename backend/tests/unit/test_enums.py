"""Unit tests for the case-insensitive string enumeration."""

import pytest

from app.domain.enums import CaseInsensitiveStrEnum


class Level(CaseInsensitiveStrEnum):
    HOURLY = "hourly"
    DAILY = "daily"


@pytest.mark.parametrize("text", ["hourly", "Hourly", "HOURLY", "hOuRlY"])
def test_any_letter_case_finds_the_member(text: str) -> None:
    assert Level(text) is Level.HOURLY
    assert Level(text).value == "hourly"


@pytest.mark.parametrize("text", ["weekly", ""])
def test_unknown_values_are_still_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="is not a valid Level"):
        Level(text)


def test_values_that_are_not_text_find_nothing() -> None:
    assert Level._missing_(1) is None
    assert Level._missing_(None) is None
