"""Startup sequence of the cache database."""

import logging
from pathlib import Path

from sqlalchemy import Engine

from app.db.engine import create_sqlite_engine, enable_wal
from app.db.schema import SCHEMA_VERSION, ensure_schema

logger = logging.getLogger(__name__)


def open_database(path: Path, data_source: str) -> Engine:
    """Create the engine, enable WAL and make sure the schema is current for ``data_source``.

    The caller owns the engine and must call ``engine.dispose()`` at shutdown.
    """
    engine = create_sqlite_engine(path)
    try:
        enable_wal(engine)
        action = ensure_schema(engine, data_source)
    except Exception:
        engine.dispose()
        raise
    logger.info(
        "Cache database %s: schema version %s (%s), data source %r.",
        path,
        SCHEMA_VERSION,
        action,
        data_source,
    )
    return engine
