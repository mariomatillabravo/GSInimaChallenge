"""FastAPI dependencies: how endpoints obtain configuration and services.

The objects are built once at startup (see ``app.main``) and stored in ``app.state``. Tests
replace them through ``app.dependency_overrides`` without touching the endpoints.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.services.measurements import MeasurementService


def get_settings(request: Request) -> Settings:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured.")
    return settings


def get_measurement_service(request: Request) -> MeasurementService:
    service = request.app.state.measurement_service
    if not isinstance(service, MeasurementService):
        raise RuntimeError("The measurement service is not configured.")
    return service


SettingsDep = Annotated[Settings, Depends(get_settings)]
MeasurementServiceDep = Annotated[MeasurementService, Depends(get_measurement_service)]
