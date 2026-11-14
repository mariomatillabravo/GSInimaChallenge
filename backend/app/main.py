"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import health


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Using a factory (instead of configuring a module-level app directly) lets tests create a fresh,
    isolated application and, later, inject alternative settings or dependencies.
    """
    app = FastAPI(
        title="AEMET Antarctica Weather API",
        version="0.1.0",
        description=(
            "Retrieves, caches and aggregates weather data from the Spanish Antarctic stations "
            "published by AEMET OpenData."
        ),
    )
    app.include_router(health.router)
    return app


app = create_app()
