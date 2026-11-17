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
from fastapi.middleware.gzip import GZipMiddleware

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes import health, measurements, meta, stations
from app.clients.aemet import AemetAntarcticaClient
from app.clients.recorded import RecordedWeatherSource
from app.core.config import Settings
from app.core.logs import configure_logging
from app.db.database import open_database
from app.db.repository import CacheRepository
from app.domain.sources import WeatherSource
from app.services.measurements import MeasurementService, SourceLabel


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    Using a factory instead of a module-level app lets tests build isolated applications with
    their own settings, and makes invalid configuration fail at startup with a clear message.

    Args:
        settings: Configuration to use. When omitted, it is read from the environment.
    """
    app = FastAPI(
        title="AEMET Antarctica Weather API",
        version="1.1.0",
        description=(
            "Retrieves and aggregates weather data from the Spanish Antarctic stations published "
            "by AEMET OpenData. Output datetimes are in Europe/Madrid with their UTC offset."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings if settings is not None else Settings()
    configure_logging(app.state.settings.log_level, app.state.settings.log_format)
    # Repetitive JSON compresses very well; tiny responses are not worth the CPU.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # Added last, so it is the outermost: it sees every request and times the whole of it.
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(stations.router)
    app.include_router(measurements.router)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create long-lived resources at startup and release them at shutdown.

    Startup runs before the server accepts requests, so its short blocking steps (opening the
    SQLite file) hold up no request.
    """
    settings: Settings = app.state.settings
    label = _source_label(settings)
    with ExitStack() as resources:
        engine = open_database(settings.cache_db_file, data_source=label)
        resources.callback(engine.dispose)
        app.state.db_engine = engine
        app.state.measurement_service = MeasurementService(
            _build_source(settings, resources),
            source_label=label,
            repository=CacheRepository(engine),
            policy=settings.freshness_policy,
            cooldown=settings.upstream_cooldown,
        )
        yield


def _source_label(settings: Settings) -> SourceLabel:
    return "demo" if settings.demo_mode else "aemet"


def _build_source(settings: Settings, resources: ExitStack) -> WeatherSource:
    """Recorded responses in demo mode, the real AEMET client otherwise."""
    if settings.demo_mode:
        return RecordedWeatherSource(settings.demo_data_dir)
    if settings.aemet_api_key is None:  # already rejected by Settings; keeps the types exact
        raise RuntimeError("AEMET_API_KEY is required when DEMO_MODE is false.")
    # One HTTP client (connection pool) shared by every request, closed at shutdown.
    http = resources.enter_context(httpx.Client(timeout=settings.aemet_timeout_seconds))
    return AemetAntarcticaClient(
        http,
        api_key=settings.aemet_api_key,
        base_url=settings.aemet_base_url,
        max_attempts=settings.aemet_max_attempts,
    )
