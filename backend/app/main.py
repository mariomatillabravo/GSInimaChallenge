"""FastAPI application entry point.

Run it through the factory so that configuration is loaded (and validated) at startup:

    uvicorn app.main:create_app --factory
"""

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import Settings


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
            "Retrieves, caches and aggregates weather data from the Spanish Antarctic stations "
            "published by AEMET OpenData."
        ),
    )
    app.state.settings = settings if settings is not None else Settings()
    app.include_router(health.router)
    return app
