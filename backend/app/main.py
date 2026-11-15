"""FastAPI application entry point and composition root.

This is the only module that decides which concrete implementations are used (real AEMET client
or recorded data) and wires them together. Run it through the factory so that configuration is
loaded and validated at startup:

    uvicorn app.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import health, measurements, stations
from app.clients.aemet import AemetAntarcticaClient
from app.clients.recorded import RecordedWeatherSource
from app.core.config import Settings
from app.services.measurements import MeasurementService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    Using a factory instead of a module-level app lets tests build isolated applications with
    their own settings, and makes invalid configuration fail at startup with a clear message.

    Args:
        settings: Configuration to use. When omitted, it is read from the environment.
    """
    app = FastAPI(
        title="AEMET Antarctica Weather API",
        version="0.1.0",
        description=(
            "Retrieves and aggregates weather data from the Spanish Antarctic stations published "
            "by AEMET OpenData. Output datetimes are in Europe/Madrid with their UTC offset."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings if settings is not None else Settings()
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(stations.router)
    app.include_router(measurements.router)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create long-lived resources at startup and release them at shutdown."""
    with ExitStack() as resources:
        app.state.measurement_service = _build_measurement_service(app.state.settings, resources)
        yield


def _build_measurement_service(settings: Settings, resources: ExitStack) -> MeasurementService:
    if settings.demo_mode:
        return MeasurementService(
            RecordedWeatherSource(settings.demo_data_dir), source_label="demo"
        )
    if settings.aemet_api_key is None:  # already rejected by Settings; keeps the types exact
        raise RuntimeError("AEMET_API_KEY is required when DEMO_MODE is false.")
    # One HTTP client (connection pool) shared by every request, closed at shutdown.
    http = resources.enter_context(httpx.Client(timeout=settings.aemet_timeout_seconds))
    client = AemetAntarcticaClient(
        http,
        api_key=settings.aemet_api_key,
        base_url=settings.aemet_base_url,
        max_attempts=settings.aemet_max_attempts,
    )
    return MeasurementService(client, source_label="aemet")
