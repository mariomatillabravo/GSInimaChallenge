"""Enumerations shared by the domain and the API."""

from enum import StrEnum
from typing import Self


class CaseInsensitiveStrEnum(StrEnum):
    """A string enumeration whose values match in any letter case: ``Hourly`` is ``hourly``.

    Values are written in lower case. Python calls ``_missing_`` when a value is not found, and
    Pydantic (so FastAPI's query parameters) goes through it too, while the OpenAPI document still
    lists the canonical values.
    """

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if isinstance(value, str):
            lowered = value.lower()
            for member in cls:
                if member.value == lowered:
                    return member
        return None
