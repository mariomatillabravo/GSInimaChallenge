"""Liveness endpoint used by Docker, CI smoke tests and load balancers."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Payload returned by the liveness check."""

    status: Literal["ok"]


@router.get("/health", summary="Liveness check")
def get_health() -> HealthResponse:
    """Confirm that the process is up and able to serve requests.

    This is a liveness check only: it does not verify external dependencies such as the database
    or the AEMET API.
    """
    return HealthResponse(status="ok")
